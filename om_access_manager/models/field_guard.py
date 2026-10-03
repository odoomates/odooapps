# Hidden and read-only fields, enforced only on the methods a client or script
# calls itself, never from Python: Odoo 20 checks field access on every Python
# read, so denying them in _has_field_access() would break business code.
# Hidden values are blanked, not removed, so views referring to them keep working.
import threading

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import request

AGGREGATE_SEPARATOR = ':'
# the summary of extra totals lines of a quotation (sale.order)
EXTRA_TOTALS = 'extra_total_fields'
DOMAIN_SUBQUERY_OPERATORS = ('any', 'not any', 'any!', 'not any!')


def mark_rpc_entry(model_name, method):
    """ Record, on the current request, the method a client called. """
    if request:
        request.om_rpc_entry = (model_name, method)


class Base(models.AbstractModel):
    _inherit = 'base'

    #
    # what the guard needs
    #

    def _om_rpc_entry(self, method):
        """ Whether ``method`` of this model is the call the client or the script made. """
        if self.env.su:
            return False
        if request:
            entry = getattr(request, 'om_rpc_entry', None)
            return bool(entry) and entry[0] == self._name and entry[1] in (method, '*')
        marker = getattr(threading.current_thread(), 'rpc_model_method', None)
        return marker == f'{self._name}.{method}'

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
        raise AccessError(_(
            "Your access profile does not allow using the field '%(field)s' of '%(model)s'.",
            field=field.string if field else field_name,
            model=self.env['ir.model']._get(model_name).name or model_name))

    def _om_check_path(self, rules, path):
        """ Refuse a dotted path (``partner_id.user_id.name``) that crosses a hidden field.
        An aggregate (``amount:sum``) or a language (``name@fr_FR``) does not hide it. """
        model = self
        path = path.split(':')[0]
        for name in path.split('.'):
            name = name.split('@')[0]
            if name in self._om_hidden(rules, model._name):
                self._om_refuse(model._name, name)
            field = model._fields.get(name)
            if field is None or not field.relational:
                return
            model = self.env[field.comodel_name]

    def _om_check_domain(self, rules, domain):
        if isinstance(domain, Domain):
            # a domain already parsed (the /json routes pass one)
            for condition in domain.iter_conditions():
                self._om_check_path(rules, condition.field_expr)
                if isinstance(condition.value, Domain):
                    comodel = self._om_comodel_of(condition.field_expr)
                    if comodel is not None:
                        comodel._om_check_domain(rules, condition.value)
            return
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

    def _om_drop_locked(self, rules, vals):
        """ ``vals`` without the read-only and hidden fields, at every level:
        the lines written through a one2many are checked too. """
        if not isinstance(vals, dict):
            return vals
        locked = self._om_locked(rules, self._name)
        result = {}
        for name, value in vals.items():
            if name in locked:
                continue
            field = self._fields.get(name)
            if field is not None and field.type in ('one2many', 'many2many') and isinstance(value, (list, tuple)):
                comodel = self.env[field.comodel_name]
                value = [
                    (command[0], command[1], comodel._om_drop_locked(rules, command[2]), *command[3:])
                    if isinstance(command, (list, tuple)) and len(command) > 2 and isinstance(command[2], dict)
                    else command
                    for command in value
                ]
            result[name] = value
        return result

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

    def web_read(self, specification):
        rules = self._om_rpc_entry('web_read') and self._om_field_rules()
        result = super().web_read(specification)
        return self._om_blank(rules, result, specification) if rules else result

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        rules = self._om_rpc_entry('web_search_read') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        result = super().web_search_read(
            domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit)
        if rules:
            self._om_blank(rules, result.get('records', []), specification)
        return result

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        rules = self._om_rpc_entry('search') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def search_count(self, domain, limit=None):
        rules = self._om_rpc_entry('search_count') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
        return super().search_count(domain, limit=limit)

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        rules = self._om_rpc_entry('formatted_read_group') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_domain(rules, having)
            self._om_check_specs(rules, groupby)
            self._om_check_specs(rules, aggregates)
            self._om_check_order(rules, order)
        return super().formatted_read_group(
            domain, groupby=groupby, aggregates=aggregates, having=having, offset=offset, limit=limit,
            order=order)

    @api.model
    def web_read_group(self, domain, groupby, aggregates=(), limit=None, offset=0, order=None, **kwargs):
        rules = self._om_rpc_entry('web_read_group') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_specs(rules, groupby)
            self._om_check_specs(rules, aggregates)
            self._om_check_order(rules, order)
        result = super().web_read_group(
            domain, groupby, aggregates=aggregates, limit=limit, offset=offset, order=order, **kwargs)
        if rules:
            specification = kwargs.get('unfold_read_specification') or {}
            stack = list(result.get('groups', []))
            groupby_specs = kwargs.get('groupby_read_specification') or {}
            while stack:
                group = stack.pop()
                self._om_blank(rules, group.get('__records', []), specification)
                # the values read for a grouped relation (groupby_read_specification)
                if isinstance(group.get('__values'), dict):
                    for name, spec in groupby_specs.items():
                        field = self._fields.get(name)
                        if field is not None and field.relational:
                            self.env[field.comodel_name]._om_blank(rules, [group['__values']], spec)
                stack.extend(group.get('__groups', {}).get('groups', [])
                             if isinstance(group.get('__groups'), dict) else group.get('__groups', []))
        return result

    @api.model
    def read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        rules = self._om_rpc_entry('read_group') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_domain(rules, having)
            self._om_check_specs(rules, groupby)
            self._om_check_specs(rules, aggregates)
            self._om_check_order(rules, order)
        return super().read_group(
            domain, groupby=groupby, aggregates=aggregates, having=having, offset=offset, limit=limit,
            order=order)

    @api.model
    def web_name_search(self, name, specification, domain=None, operator='ilike', limit=100):
        rules = self._om_rpc_entry('web_name_search') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
        result = super().web_name_search(name, specification, domain=domain, operator=operator, limit=limit)
        return self._om_blank(rules, result, specification) if rules else result

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        rules = self._om_rpc_entry('name_search') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
        return super().name_search(name, domain=domain, operator=operator, limit=limit)

    def export_data(self, fields_to_export):
        rules = self._om_rpc_entry('export_data') and self._om_field_rules()
        if rules:
            for path in fields_to_export:
                self._om_check_path(rules, path.replace('/', '.').removesuffix('.id'))
        return super().export_data(fields_to_export)

    @api.model
    def read_progress_bar(self, domain, group_by, progress_bar):
        rules = self._om_rpc_entry('read_progress_bar') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_specs(rules, [group_by, (progress_bar or {}).get('field') or '',
                                         (progress_bar or {}).get('sum_field') or ''])
        return super().read_progress_bar(domain, group_by, progress_bar)

    @api.model
    def formatted_read_grouping_sets(self, domain, grouping_sets, aggregates=(), **kwargs):
        rules = self._om_rpc_entry('formatted_read_grouping_sets') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            for grouping_set in grouping_sets or ():
                self._om_check_specs(rules, grouping_set)
            self._om_check_specs(rules, aggregates)
            self._om_check_order(rules, kwargs.get('order'))
        return super().formatted_read_grouping_sets(domain, grouping_sets, aggregates=aggregates, **kwargs)

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

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        rules = self._om_rpc_entry('search_fetch') and self._om_field_rules()
        if rules:
            self._om_check_domain(rules, domain)
            self._om_check_order(rules, order)
        return super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)

    def copy_data(self, default=None):
        rules = self._om_rpc_entry('copy_data') and self._om_field_rules()
        result = super().copy_data(default)
        return self._om_blank(rules, result) if rules else result

    def get_field_translations(self, field_name, langs=None):
        rules = self._om_rpc_entry('get_field_translations') and self._om_field_rules()
        if rules:
            self._om_check_path(rules, field_name)
        return super().get_field_translations(field_name, langs=langs)

    def web_resequence(self, specification, field_name='sequence', offset=0):
        rules = self._om_rpc_entry('web_resequence') and self._om_field_rules()
        if rules and field_name in self._om_locked(rules, self._name):
            self._om_refuse(self._name, field_name)
        result = super().web_resequence(specification, field_name=field_name, offset=offset)
        return self._om_blank(rules, result, specification) if rules else result

    def onchange_batch(self, values_list, field_names, fields_spec):
        rules = self._om_rpc_entry('onchange_batch') and self._om_field_rules()
        result = super().onchange_batch(values_list, field_names, fields_spec)
        if rules:
            self._om_blank(rules, [item.get('value') for item in result
                                   if isinstance(item, dict) and isinstance(item.get('value'), dict)], fields_spec)
        return result

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
    def _has_field_access(self, field, operation):
        # /web/content and /web/image only ask this. Limited to binary fields:
        # Odoo's own code reads the other types as the user.
        if (operation == 'read' and field.type in ('binary', 'image') and not self.env.su
                and super()._has_field_access(field, operation)):
            rules = self.env['om.access.profile']._current_rules()
            if rules.enabled and field.name in self._om_hidden(rules, self._name):
                return False
        return super()._has_field_access(field, operation)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields=allfields, attributes=attributes)
        rules = self._om_rpc_entry('fields_get') and self._om_field_rules()
        if rules:
            for name in self._om_hidden(rules, self._name):
                result.pop(name, None)
        return result

    #
    # writing
    #

    def onchange(self, values, field_names, fields_spec):
        rules = self._om_rpc_entry('onchange') and self._om_field_rules()
        result = super().onchange(values, field_names, fields_spec)
        if rules and isinstance(result.get('value'), dict):
            self._om_blank(rules, [result['value']], fields_spec)
        return result

    def web_save(self, vals, specification, next_id=None):
        rules = self._om_rpc_entry('web_save') and self._om_field_rules()
        if rules:
            vals = self._om_drop_locked(rules, vals)
        result = super().web_save(vals, specification, next_id=next_id)
        return self._om_blank(rules, result, specification) if rules else result

    def write(self, vals):
        rules = self._om_rpc_entry('write') and self._om_field_rules()
        if rules:
            vals = self._om_drop_locked(rules, vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        rules = self._om_rpc_entry('create') and self._om_field_rules()
        if rules:
            vals_list = [self._om_drop_locked(rules, vals) for vals in vals_list]
        return super().create(vals_list)
