# Hidden and read-only fields, enforced only on the methods a client or script
# calls itself, never from Python: Odoo 20 checks field access on every Python
# read, so refusing them deeper would break business code.
# Hidden values are blanked, not removed, so views referring to them keep working.
# Which call a client made (_om_rpc_entry) is told by om_user_audit.
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.osv import expression
from odoo.tools.safe_eval import datetime, safe_eval, time

from .conditions import condition_domain
from .value_filters import names_read

_logger = logging.getLogger(__name__)

AGGREGATE_SEPARATOR = ':'
# the summary of extra totals lines of a quotation (sale.order)
EXTRA_TOTALS = 'extra_total_fields'
DOMAIN_SUBQUERY_OPERATORS = ('any', 'not any', 'any!', 'not any!')


def onchange_specification(field_onchange):
    """ The fields of an onchange (``order_line``, ``order_line.price_unit``)
    nested as Odoo 17's specification: {'order_line': {'fields': {'price_unit': {}}}}. """
    specification = {}
    for path in field_onchange or ():
        node = specification
        for name in path.split('.'):
            node = node.setdefault('fields', {}).setdefault(name, {}) if node is not specification \
                else node.setdefault(name, {})
    return specification


class RecordValues:
    """ The values of a record being saved, as the web client gives them to a
    domain: what is written, else what the record holds, else the default;
    ``parent.<field>`` in the lines of a one2many. """

    def __init__(self, model, vals, record=None, parent=None):
        self._model, self._vals, self._record, self._parent = model, vals, record, parent

    def get(self, name):
        field = self._model._fields.get(name)
        if name in self._vals and not (field and field.type in ('one2many', 'many2many')):
            value = self._vals[name]
            return value.id if isinstance(value, models.BaseModel) else value
        if self._record:
            value = self._record.sudo()[name]
        else:
            value = self._model.default_get([name]).get(name, False)
            if field and field.type in ('one2many', 'many2many'):
                return []
        if isinstance(value, models.BaseModel):
            return value.ids if field.type in ('one2many', 'many2many') else value.id
        return value

    def __getattr__(self, name):
        if name.startswith('_') or name not in self._model._fields:
            raise AttributeError(name)
        return self.get(name)


class Base(models.AbstractModel):
    _inherit = 'base'

    #
    # what the guard needs
    #

    def _om_field_rules(self):
        rules = self.env['om.access.profile']._current_rules()
        return rules if rules.enabled and rules.restricts_fields() else None

    @api.model
    def _om_hidden(self, rules, model_name):
        return rules.fields_in_modes(model_name, ('hide',))

    @api.model
    def _om_locked(self, rules, model_name):
        return rules.fields_in_modes(model_name, ('hide', 'readonly'))

    def _om_refuse(self, model_name, field_name):
        model = self.env[model_name]
        field = model._fields.get(field_name)
        raise self.env['om.access.profile']._om_refusal(_(
            "Your access profile does not allow using the field '%(field)s' of '%(model)s'.",
            field=field.string if field else field_name,
            model=self.env['ir.model']._get(model_name).name or model_name), model=model_name)

    def _om_hidden_any(self, rules):
        """ Hidden always or under a condition: filtering, grouping or exporting on
        it would tell the hidden values apart, so both are refused there. """
        return self._om_hidden(rules, self._name) | set(rules.conditional_fields(self._name, ('hide',)))

    def _om_matching(self, condition, ids):
        """ The ids among ``ids`` whose record matches a rule's condition. """
        if not ids:
            return set()
        domain = condition_domain(condition, self, self.env.uid)
        return set(self.browse(ids).sudo().exists().filtered_domain(domain).ids)

    def _om_check_path(self, rules, path):
        """ Refuse a dotted path (``partner_id.user_id.name``) that crosses a hidden field.
        An aggregate (``amount:sum``) or a language (``name@fr_FR``) does not hide it. """
        model = self
        path = path.split(':')[0]
        for name in path.split('.'):
            name = name.split('@')[0]
            if name in model._om_hidden_any(rules):
                self._om_refuse(model._name, name)
            field = model._fields.get(name)
            if field is None or not field.relational:
                return
            model = self.env[field.comodel_name]

    def _om_check_domain(self, rules, domain):
        if not domain or not isinstance(domain, (list, tuple)):
            return
        for leaf in domain:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and isinstance(leaf[0], str):
                path, operator, value = leaf
                self._om_check_path(rules, path)
                if operator in DOMAIN_SUBQUERY_OPERATORS and isinstance(value, (list, tuple)):
                    # the condition of an 'any' applies to the records at the end of the path
                    model = self
                    for name in path.split('.'):
                        field = model._fields.get(name)
                        if field is None or not field.relational:
                            break
                        model = self.env[field.comodel_name]
                    else:
                        model._om_check_domain(rules, value)

    def _om_comodel_of(self, path):
        """ The model at the end of a relational path, or None. """
        model = self
        for name in path.split('.'):
            field = model._fields.get(name)
            if field is None or not field.relational:
                return None
            model = self.env[field.comodel_name]
        return model

    def _om_check_order(self, rules, order):
        for part in (order or '').split(','):
            name = part.strip().split(' ')[0]
            if name:
                self._om_check_path(rules, name)

    def _om_check_specs(self, rules, specs):
        """ Group-bys and aggregates: ``date:month``, ``amount:sum``, ``partner_id.name``. """
        for spec in specs or ():
            if isinstance(spec, str) and spec != '__count':
                self._om_check_path(rules, spec.split(AGGREGATE_SEPARATOR)[0])

    def _om_blank(self, rules, rows, specification=None):
        """ Blank the hidden fields of ``rows`` (dicts of values), and of the
        records nested in them along ``specification``, in place. """
        hidden = self._om_hidden(rules, self._name)
        # hidden under a condition: blanked on the records matching it
        for name, condition in rules.conditional_fields(self._name, ('hide',)).items():
            ids = [row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), int)
                   and name in row]
            matching = self._om_matching(condition, ids)
            for row in rows:
                if isinstance(row, dict) and row.get('id') in matching:
                    field = self._fields.get(name)
                    row[name] = [] if field is not None and field.type in ('one2many', 'many2many') else False
        for row in rows:
            if not isinstance(row, dict):
                continue
            if hidden and isinstance(row.get(EXTRA_TOTALS), list):
                self._om_strip_extra_totals(row, hidden)
            for name in hidden:
                if name in row:
                    field = self._fields.get(name)
                    row[name] = [] if field is not None and field.type in ('one2many', 'many2many') else False
            for name, sub in (specification or {}).items():
                field = self._fields.get(name)
                if (name in hidden or field is None or not field.relational
                        or not isinstance(sub, dict) or not sub.get('fields')):
                    continue
                comodel = self.env[field.comodel_name]
                value = row.get(name)
                if isinstance(value, dict):
                    comodel._om_blank(rules, [value], sub['fields'])
                elif isinstance(value, list):
                    nested = []
                    for item in value:
                        if isinstance(item, dict):
                            nested.append(item)
                        elif isinstance(item, (list, tuple)) and len(item) > 2 and isinstance(item[2], dict):
                            # onchange answers with commands: (command, id, values)
                            nested.append(item[2])
                    comodel._om_blank(rules, nested, sub['fields'])
        return rows

    def _om_strip_extra_totals(self, row, hidden):
        """ Remove the totals summary lines that show a hidden field (e.g. the
        margin line under a quotation), matched by label or by value. """
        labels = [self._fields[name]._description_string(self.env) for name in hidden if name in self._fields]
        values = set()
        if isinstance(row.get('id'), int):
            record = self.browse(row['id']).sudo().exists()
            for name in hidden:
                field = self._fields.get(name)
                if record and field is not None and field.type in ('float', 'monetary') and record[name]:
                    values.add(record[name])
        for group in row[EXTRA_TOTALS]:
            if isinstance(group, dict) and isinstance(group.get('lines'), list):
                group['lines'] = [
                    line for line in group['lines']
                    if not (isinstance(line, dict) and (
                        line.get('value') in values
                        or any(str(line.get('label') or '').startswith(label) for label in labels if label)))
                ]

    def _om_drop_locked(self, rules, vals, record=None):
        """ ``vals`` without the read-only and hidden fields, at every level:
        the lines written through a one2many are checked too. A field locked
        under a condition is dropped when ``record`` (the record written)
        matches it. """
        if not isinstance(vals, dict):
            return vals
        locked = set(self._om_locked(rules, self._name))
        if record:
            locked |= {
                name for name, condition in rules.conditional_fields(self._name, ('hide', 'readonly')).items()
                if name in vals and self._om_matching(condition, record.ids)
            }
        result = {}
        for name, value in vals.items():
            if name in locked:
                continue
            field = self._fields.get(name)
            if field is not None and field.type in ('one2many', 'many2many') and isinstance(value, (list, tuple)):
                comodel = self.env[field.comodel_name]
                value = [
                    (command[0], command[1],
                     comodel._om_drop_locked(
                         rules, command[2],
                         comodel.browse(command[1]) if command[0] == 1 and isinstance(command[1], int) else None),
                     *command[3:])
                    if isinstance(command, (list, tuple)) and len(command) > 2 and isinstance(command[2], dict)
                    else command
                    for command in value
                ]
            result[name] = value
        return result

    #
    # value filters
    #

    def _om_value_rules(self):
        rules = self.env['om.access.profile']._current_rules()
        return rules if rules.enabled and rules.has_value_filters() else None

    def _om_check_values(self, rules, vals, record=None, parent=None):
        """ Refuse a value outside the value filter of its field, in ``vals``
        and in the lines written through a one2many or a many2many. """
        if not isinstance(vals, dict):
            return
        values = RecordValues(self, vals, record, parent)
        for name, value in vals.items():
            field = self._fields.get(name)
            if field is None or not field.relational:
                continue
            domain = rules.field_domain(self._name, name)
            if domain:
                ids = self._om_new_ids(field, value, record)
                if ids:
                    self._om_check_value(name, domain, ids, values)
            if field.type in ('one2many', 'many2many') and isinstance(value, (list, tuple)):
                comodel = self.env[field.comodel_name]
                for command in value:
                    if isinstance(command, (list, tuple)) and len(command) > 2 and isinstance(command[2], dict):
                        line = comodel.browse(command[1]) if command[0] == Command.UPDATE else None
                        comodel._om_check_values(rules, command[2], line, values)

    @api.model
    def _om_new_ids(self, field, value, record=None):
        """ The ids a value of a relational field links, leaving out the ones
        the record already had: a filter only judges what changes. """
        if field.type == 'many2one':
            value = value.id if isinstance(value, models.BaseModel) else value
            if not isinstance(value, int) or isinstance(value, bool) or not value:
                return set()
            if record and len(record) == 1 and record.sudo()[field.name].id == value:
                return set()
            return {value}
        if not isinstance(value, (list, tuple)):
            return set()
        ids = set()
        for command in value:
            if isinstance(command, int) and not isinstance(command, bool):
                ids.add(command)
            elif isinstance(command, (list, tuple)) and command:
                if command[0] == Command.LINK and len(command) > 1 and isinstance(command[1], int):
                    ids.add(command[1])
                elif command[0] == Command.SET and len(command) > 2 and isinstance(command[2], (list, tuple)):
                    ids.update(i for i in command[2] if isinstance(i, int) and not isinstance(i, bool))
        if ids and record:
            for current in record.sudo():
                ids -= set(current[field.name].ids)
        return ids

    def _om_check_value(self, name, domain, ids, values):
        field = self._fields[name]
        context = {
            'context': dict(self.env.context),
            'uid': self.env.uid,
            'allowed_company_ids': self.env.companies.ids,
            'current_company_id': self.env.company.id,
            'datetime': datetime,
            'time': time,
            'relativedelta': relativedelta,
            'context_today': lambda: fields.Date.context_today(self),
            'parent': values._parent,
        }
        try:
            for key in names_read(domain) - set(context):
                if key in self._fields:
                    context[key] = values.get(key)
            filtered = expression.normalize_domain(safe_eval(domain, context))
        except Exception:  # noqa: BLE001
            # a filter the server cannot evaluate on its own stays a filter of the dropdown
            _logger.debug("Value filter %r of %s.%s not checked", domain, self._name, name, exc_info=True)
            return
        comodel = self.env[field.comodel_name].sudo().with_context(active_test=False)
        allowed = comodel.search(expression.AND([[('id', 'in', list(ids))], filtered])).ids
        if set(allowed) != set(ids):
            raise self.env['om.access.profile']._om_refusal(_(
                "Your access profile does not allow this value for the field '%(field)s' of '%(model)s'.",
                field=field._description_string(self.env),
                model=self.env['ir.model']._get(self._name).name or self._name),
                model=self._name, method=name)

    #
    # reading
    #

    def read(self, fields=None, load='_classic_read'):
        rules = self._om_rpc_entry('read') and self._om_field_rules()
        result = super().read(fields, load=load)
        return self._om_blank(rules, result) if rules else result

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        rules = self._om_rpc_entry('search_read') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        result = super().search_read(domain, fields, offset=offset, limit=limit, order=order, **read_kwargs)
        return self._om_blank(rules, result) if rules else result

    @api.model
    def web_search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, count_limit=None):
        rules = self._om_rpc_entry('web_search_read') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        result = super().web_search_read(
            domain, fields, offset=offset, limit=limit, order=order, count_limit=count_limit)
        if rules:
            self._om_blank(rules, result.get('records', []))
        return result

    @api.model
    def search(self, domain, offset=0, limit=None, order=None, count=False):
        rules = self._om_rpc_entry('search') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        return super().search(domain, offset=offset, limit=limit, order=order, count=count)

    @api.model
    def search_count(self, domain, limit=None):
        rules = self._om_rpc_entry('search_count') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
        return super().search_count(domain, limit=limit)

    @api.model
    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=False, lazy=True,
                       **kwargs):
        rules = self._om_rpc_entry('web_read_group') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_specs(rules, [groupby] if isinstance(groupby, str) else groupby)
            self._om_check_specs(rules, fields)
            self._om_check_order(rules, orderby)
        return super().web_read_group(domain, fields, groupby, limit=limit, offset=offset, orderby=orderby,
                                      lazy=lazy, **kwargs)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        rules = self._om_rpc_entry('read_group') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_specs(rules, [groupby] if isinstance(groupby, str) else groupby)
            self._om_check_specs(rules, fields)
            self._om_check_order(rules, orderby)
        return super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby,
                                  lazy=lazy)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        rules = self._om_rpc_entry('name_search') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, args)
        return super().name_search(name, args=args, operator=operator, limit=limit)

    def export_data(self, fields_to_export):
        rules = self._om_rpc_entry('export_data') and self._om_field_rules()
        if rules:
            for path in fields_to_export:
                self._om_check_path(rules, path.replace('/', '.').removesuffix('.id'))
                self._om_check_export_path(rules, path.replace('/', '.').removesuffix('.id'))
        return super().export_data(fields_to_export)

    def _om_check_export_path(self, rules, path):
        """ Refuse a path crossing a field kept out of the exports. """
        model = self
        for name in path.split('.'):
            name = name.split('@')[0]
            if name in rules.not_exported(model._name):
                field = model._fields.get(name)
                raise self.env['om.access.profile']._om_refusal(_(
                    "Your access profile does not allow exporting the field '%(field)s' of '%(model)s'.",
                    field=field.string if field else name,
                    model=self.env['ir.model']._get(model._name).name or model._name), model=model._name)
            field = model._fields.get(name)
            if field is None or not field.relational:
                return
            model = self.env[field.comodel_name]

    @api.model
    def read_progress_bar(self, domain, group_by, progress_bar):
        rules = self._om_rpc_entry('read_progress_bar') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_specs(rules, [group_by, (progress_bar or {}).get('field') or '',
                                         (progress_bar or {}).get('sum_field') or ''])
        return super().read_progress_bar(domain, group_by, progress_bar)

    def _om_check_search_panel(self, method, field_name, kwargs):
        rules = self._om_rpc_entry(method) and self._om_field_rules()
        if rules:
            self._om_check_path(rules, field_name)
            for key in ('search_domain', 'category_domain', 'filter_domain'):
                self._om_check_domain(rules, kwargs.get(key))

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        self._om_check_search_panel('search_panel_select_range', field_name, kwargs)
        return super().search_panel_select_range(field_name, **kwargs)

    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        self._om_check_search_panel('search_panel_select_multi_range', field_name, kwargs)
        return super().search_panel_select_multi_range(field_name, **kwargs)

    def copy_data(self, default=None):
        rules = self._om_rpc_entry('copy_data') and self._om_field_rules()
        result = super().copy_data(default)
        return self._om_blank(rules, result) if rules else result

    def get_field_translations(self, field_name, langs=None):
        rules = self._om_rpc_entry('get_field_translations') and self._om_field_rules()
        if rules:
            self._om_check_path(rules, field_name)
        return super().get_field_translations(field_name, langs=langs)

    @api.model
    def load(self, fields, data):
        rules = self._om_rpc_entry('load') and self._om_field_rules()
        if rules:
            # an import names its columns by path: order_line/price_unit
            for path in fields:
                self._om_check_locked_path(rules, path.replace('/', '.').removesuffix('.id'))
        return super().load(fields, data)

    def copy(self, default=None):
        rules = self._om_rpc_entry('copy') and self._om_field_rules()
        if rules and default:
            default = self._om_drop_locked(rules, default)
        return super().copy(default)

    def _om_check_locked_path(self, rules, path):
        model = self
        for name in path.split('.'):
            name = name.split('@')[0]
            if name in self._om_locked(rules, model._name):
                self._om_refuse(model._name, name)
            field = model._fields.get(name)
            if field is None or not field.relational:
                return
            model = self.env[field.comodel_name]

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields=allfields, attributes=attributes)
        rules = self._om_rpc_entry('fields_get') and self._om_field_rules()
        if rules:
            for name in self._om_hidden_any(rules):
                result.pop(name, None)
            # the Export dialog leaves out what is not exportable
            for name in rules.not_exported(self._name):
                if name in result:
                    result[name]['exportable'] = False
        return result

    #
    # writing
    #

    def onchange(self, values, field_name, field_onchange):
        rules = self._om_rpc_entry('onchange') and self._om_field_rules()
        result = super().onchange(values, field_name, field_onchange)
        if rules and isinstance(result.get('value'), dict):
            self._om_blank(rules, [result['value']], onchange_specification(field_onchange))
        return result

    def write(self, vals):
        if self._om_rpc_entry('write') and (value_rules := self._om_value_rules()):
            for record in self:
                self._om_check_values(value_rules, vals, record)
        rules = self._om_rpc_entry('write') and self._om_field_rules()
        if rules:
            conditional = rules.conditional_fields(self._name, ('hide', 'readonly'))
            if conditional and not conditional.keys().isdisjoint(vals):
                # what may be written differs from a record to another
                for record in self:
                    super(Base, record).write(self._om_drop_locked(rules, vals, record))
                return True
            vals = self._om_drop_locked(rules, vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if self._om_rpc_entry('create') and (value_rules := self._om_value_rules()):
            for vals in vals_list:
                self._om_check_values(value_rules, vals)
        rules = self._om_rpc_entry('create') and self._om_field_rules()
        if rules:
            vals_list = [self._om_drop_locked(rules, vals) for vals in vals_list]
        return super().create(vals_list)


class IrBinary(models.AbstractModel):
    _inherit = 'ir.binary'

    def _get_stream_from(self, record, field_name='raw', *args, **kwargs):
        # /web/content and /web/image: a hidden file or image is refused (an
        # image shows its placeholder). Limited to binary fields: Odoo's own
        # code reads the other types as the user.
        model_field = record._fields.get(field_name)
        if model_field is not None and model_field.type in ('binary', 'image') and not record.env.su:
            rules = record.env['om.access.profile']._current_rules()
            if rules.enabled and field_name in record._om_hidden(rules, record._name):
                raise AccessError(_("Your access profile hides this file."))
        return super()._get_stream_from(record, field_name, *args, **kwargs)
