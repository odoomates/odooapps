# Odoo 19 checks the rights on a model in ir.model.access and filters the
# records in ir.rule; both are cached per user, which is where a profile
# subtracts access. Each profile carries its own hidden group, so the caches
# keyed by group sets stay right too.
from lxml import etree

from odoo import _, api, models, tools
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import config
from odoo.tools.safe_eval import safe_eval

ARCHIVE_FIELDS = frozenset({'active', 'x_active'})


def _operation_label(env, operation):
    return {
        'read': env._("read"), 'write': env._("edit"), 'create': env._("create"), 'unlink': env._("delete"),
    }.get(operation, operation)


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @tools.ormcache('self.env.uid', 'mode')
    def _get_allowed_models(self, mode='read'):
        models_allowed = super()._get_allowed_models(mode)
        rules = self.env['om.access.profile']._resolve(self.env.uid)
        if not rules.enabled:
            return models_allowed
        return frozenset(name for name in models_allowed if rules.allows(name, mode))

    def _make_access_error(self, model, mode):
        rules = self.env['om.access.profile']._resolve(self.env.uid)
        if rules.enabled and not rules.allows(model, mode):
            return AccessError(_(
                "Your access profile does not allow you to %(operation)s %(model)s.\n\n"
                "Ask your administrator if you need to.",
                operation=_operation_label(self.env, mode),
                model=self.env['ir.model']._get(model).name or model))
        return super()._make_access_error(model, mode)


class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    @tools.conditional(
        'xml' not in config['dev_mode'],
        tools.ormcache('self.env.uid', 'self.env.su', 'model_name', 'mode',
                       'tuple(self._compute_domain_context_values())'),
    )
    def _compute_domain(self, model_name, mode="read"):
        domain = super()._compute_domain(model_name, mode)
        if self.env.su or domain.is_false():
            return domain
        rules = self.env['om.access.profile']._resolve(self.env.uid)
        if not rules.enabled:
            return domain
        if not rules.allows(model_name, mode):
            return Domain.FALSE
        or_groups, and_groups = rules.record_domains(model_name, mode)
        if not or_groups and not and_groups:
            return domain
        eval_context = self.env['om.access.profile']._om_eval_context()

        def parse(terms):
            return Domain.AND([Domain(safe_eval(term, eval_context)) for term in terms])

        extra = [parse(terms) for terms in and_groups]
        if or_groups:
            extra.append(Domain.OR([parse(terms) for terms in or_groups]))
        return (domain & Domain.AND(extra)).optimize(self.env[model_name])

    def _make_access_error(self, operation, records):
        # Say plainly that the profile refused, without naming the records:
        # the user may not be allowed to know them.
        rules = self.env['om.access.profile']._resolve(self.env.uid)
        if rules.enabled and records:
            model_label = self.env['ir.model']._get(records._name).name or records._name
            core = super()._compute_domain(records._name, operation)
            if not core.is_false() and records.sudo().filtered_domain(core) == records.sudo():
                return AccessError(_(
                    "Your access profile does not allow you to %(operation)s these %(model)s "
                    "records: they are outside the ones allowed to you.\n\n"
                    "Ask your administrator if you need to.",
                    operation=_operation_label(self.env, operation), model=model_label))
        return super()._make_access_error(operation, records)


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id, view_type, **options)
        rules = self.env['om.access.profile']._current_rules()
        if not rules.enabled or not rules.affects_views():
            return result
        tree = etree.fromstring(result['arch'])
        self.env['om.access.profile']._apply_view_rules(rules, tree, self._name, view_type)
        result = dict(result, arch=etree.tostring(tree, encoding='unicode'))
        return result

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields=allfields, attributes=attributes)
        rules = self.env['om.access.profile']._current_rules()
        if not rules.enabled:
            return result
        # The client offers Archive/Unarchive only when 'active' is writable,
        # so making it read-only removes the entries.
        if rules.model_flag(self._name, 'hide_archive'):
            for field_name in ARCHIVE_FIELDS:
                if field_name in result and 'readonly' in result[field_name]:
                    result[field_name]['readonly'] = True
        for field_name in rules.restricted_fields(self._name):
            if field_name in result and rules.field_mode(self._name, field_name) == 'readonly':
                if 'readonly' in result[field_name]:
                    result[field_name]['readonly'] = True
        return result

    def write(self, vals):
        if self._name == 'hr.employee' and any(
                name.startswith('employee') for name in self.env['om.access.profile']._om_user_fields_in_filters()):
            # a filter reads the user's employee (user.employee_id.department_id...)
            self.env.registry.clear_cache('default')
        # Odoo does not enforce read-only on write, so fields_get() only hides
        # Archive/Unarchive; this is what refuses them.
        if not ARCHIVE_FIELDS.isdisjoint(vals):
            rules = self.env['om.access.profile']._current_rules()
            if rules.enabled and rules.model_flag(self._name, 'hide_archive'):
                raise UserError(_(
                    "Your access profile does not allow archiving '%s'.",
                    self.env['ir.model']._get(self._name).name or self._name))
        if self._om_changes_properties(vals):
            rules = self.env['om.access.profile']._current_rules()
            if rules.enabled and rules.has_flag('block_properties'):
                raise self.env['om.access.profile']._om_refusal(
                    _("Your access profile does not allow changing the properties of a form."),
                    model=self._name, record_ids=self.ids)
        return super().write(vals)

    def _om_changes_properties(self, vals):
        """ Whether ``vals`` changes the definition of properties: written on the
        definition itself, or carried by the values of a properties field. """
        for name, value in vals.items():
            field = self._fields.get(name)
            if field is None:
                continue
            if field.type == 'properties_definition':
                return True
            if field.type == 'properties' and isinstance(value, list) and any(
                    isinstance(item, dict) and (item.get('definition_changed') or item.get('definition_deleted'))
                    for item in value):
                return True
        return False

    def copy(self, default=None):
        # copy() goes through create(), so neither the button check nor
        # the record rules see it as a duplication.
        rules = self.env['om.access.profile']._current_rules()
        if rules.enabled and rules.model_flag(self._name, 'hide_duplicate'):
            raise UserError(_(
                "Your access profile does not allow duplicating '%s'.",
                self.env['ir.model']._get(self._name).name or self._name))
        return super().copy(default)

    @api.model
    def load(self, fields, data):
        # Every import lands here; import="0" on the view only hides the menu entry.
        rules = self.env['om.access.profile']._current_rules()
        if rules.enabled and rules.model_flag(self._name, 'hide_import'):
            raise UserError(_(
                "Your access profile does not allow importing '%s'.",
                self.env['ir.model']._get(self._name).name or self._name))
        return super().load(fields, data)

    def export_data(self, fields_to_export):
        rules = self.env['om.access.profile']._current_rules()
        if rules.enabled and rules.model_flag(self._name, 'hide_export'):
            raise UserError(_(
                "Your access profile does not allow exporting '%s'.",
                self.env['ir.model']._get(self._name).name or self._name))
        return super().export_data(fields_to_export)
