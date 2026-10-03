# _access_domain() is the one place where access can be subtracted per user in
# Odoo 20: ir.access permissions are OR-ed, so adding records never removes access.
from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

ARCHIVE_FIELDS = frozenset({'active', 'x_active'})


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    @api.ormcache('operation', 'self.env._access_context')
    def _access_domain(self, operation):
        # Not short circuited on self.env.su: the cache key lacks the superuser
        # flag, so a sudo result would be served to the same user without it.
        domain = super()._access_domain(operation)
        if domain.is_false():
            return domain

        rules = self.env['om.access.profile']._resolve(self.env.uid)
        if not rules.enabled:
            return domain
        if not rules.allows(self._name, operation):
            return Domain.FALSE

        or_groups, and_groups = rules.record_domains(self._name, operation)
        if not or_groups and not and_groups:
            return domain

        eval_context = self.env['om.access.profile']._om_eval_context()

        def parse(terms):
            return Domain.AND([Domain(safe_eval(term, eval_context)) for term in terms])

        extra = [parse(terms) for terms in and_groups]
        if or_groups:
            extra.append(Domain.OR([parse(terms) for terms in or_groups]))
        return domain & Domain.AND(extra)

    def _make_access_error_message(self, operation, domain):
        # Say plainly that the profile refused, without naming the records:
        # the user may not be allowed to know them.
        rules = self.env['om.access.profile']._current_rules()
        if rules.enabled:
            model_label = self.env['ir.model']._get(self._name).name or self._name
            if not rules.allows(self._name, operation):
                return AccessError(_(
                    "Your access profile does not allow you to %(operation)s %(model)s.\n\n"
                    "Ask your administrator if you need to.",
                    operation=self._om_operation_label(operation), model=model_label))
            core = super()._access_domain(operation)
            if self and not core.is_false() and self.sudo().filtered_domain(core) == self.sudo():
                return AccessError(_(
                    "Your access profile does not allow you to %(operation)s these %(model)s "
                    "records: they are outside the ones allowed to you.\n\n"
                    "Ask your administrator if you need to.",
                    operation=self._om_operation_label(operation), model=model_label))
        return super()._make_access_error_message(operation, domain)

    def _om_operation_label(self, operation):
        return {
            'read': _("read"), 'write': _("edit"), 'create': _("create"), 'unlink': _("delete"),
        }.get(operation, operation)

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
        # Odoo does not enforce read-only on write, so fields_get() only hides
        # Archive/Unarchive; this is what refuses them.
        if not ARCHIVE_FIELDS.isdisjoint(vals):
            rules = self.env['om.access.profile']._current_rules()
            if rules.enabled and rules.model_flag(self._name, 'hide_archive'):
                raise UserError(_(
                    "Your access profile does not allow archiving '%s'.",
                    self.env['ir.model']._get(self._name).name or self._name))
        return super().write(vals)

    def copy(self, default=None):
        # copy() goes through create(), so neither the button check nor
        # _access_domain() sees it as a duplication.
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
