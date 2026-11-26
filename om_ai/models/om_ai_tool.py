import json
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

BLOCKED_MODEL_PREFIXES = ('ir.', 'base.', 'bus.', 'om.ai.', 'res.users.apikeys', 'res.users.settings',
                          'res.users.log', 'res.device', 'auth.', 'mail.mail', 'iap.', 'payment.provider',
                          'fetchmail.', 'mail.alias')
OPERATORS = ('=', '!=', '>', '>=', '<', '<=', 'in', 'not in', 'ilike', 'not ilike', 'like', 'not like')
SKIPPED_FIELD_TYPES = ('binary', 'json', 'properties', 'properties_definition')
MAX_LIMIT = 50


class OmAiTool(models.Model):
    """A function the AI may call. The tool runs as the user who talks to the
    AI, with that user's access rights and record rules.

    To add a tool from another module, add a record and a method named
    ``_ai_tool_<something>(self, tool, **arguments)`` on this model that returns
    JSON-serialisable data."""
    _name = 'om.ai.tool'
    _description = 'AI Tool'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help='Function name given to the AI (letters, digits, underscores).')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(required=True, help='Tells the AI what the tool does and when to use it.')
    parameters_schema = fields.Text(string='Parameters (JSON Schema)', required=True,
                                    default='{"type": "object", "properties": {}}')
    method = fields.Char(required=True, help='Python method of om.ai.tool, starting with _ai_tool_.')
    read_only = fields.Boolean(string='Read Only', default=True,
                               help='Read-only tools run directly. Other tools wait for the user to confirm.')
    model_ids = fields.Many2many('ir.model', string='Allowed Models',
                                 help='Models the tool may read. Leave empty for every model the user may read.')
    group_ids = fields.Many2many('res.groups', string='Allowed Groups',
                                 help='Only users of these groups may use the tool. Empty for all AI users.')

    _code_unique = models.Constraint('UNIQUE(code)', 'The tool code must be unique.')

    @api.constrains('code', 'method', 'parameters_schema')
    def _check_definition(self):
        for tool in self:
            if not tool.code.replace('_', '').isalnum():
                raise ValidationError(self.env._('The tool code may only contain letters, digits and underscores.'))
            if not tool.method.startswith('_ai_tool_'):
                raise ValidationError(self.env._('The tool method must start with _ai_tool_.'))
            try:
                schema = json.loads(tool.parameters_schema)
            except ValueError:
                schema = None
            if not isinstance(schema, dict):
                raise ValidationError(self.env._('The parameters must be a JSON Schema object.'))

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    @api.model
    def _get_available(self, codes=None, read_only=None):
        domain = Domain('active', '=', True)
        if codes:
            domain &= Domain('code', 'in', list(codes))
        if read_only is not None:
            domain &= Domain('read_only', '=', read_only)
        tools = self.sudo().search(domain)
        user = self.env.user
        return tools.filtered(lambda tool: not tool.group_ids or tool.group_ids & user.all_group_ids).with_env(self.env)

    def _to_spec(self):
        """Tool definitions in the normalised format of the engine."""
        return [{
            'name': tool.code,
            'description': tool.description,
            'parameters': json.loads(tool.parameters_schema),
        } for tool in self.sudo()]

    def _execute(self, arguments):
        """Run the tool as the current user. Errors are returned to the AI as text."""
        self.ensure_one()
        tool = self.sudo()
        if not hasattr(type(self), tool.method) or not tool.method.startswith('_ai_tool_'):
            return {'error': 'Unknown tool method.'}
        try:
            with self.env.cr.savepoint():
                return getattr(self.with_env(self.env), tool.method)(tool, **(arguments or {}))
        except (AccessError, MissingError, UserError, ValidationError, ValueError, TypeError, KeyError) as error:
            return {'error': str(error.args[0] if error.args else error)}

    # ------------------------------------------------------------------
    # Helpers for the built-in tools
    # ------------------------------------------------------------------
    def _ai_get_model(self, tool, model_name):
        model_name = (model_name or '').strip()
        if model_name not in self.env or model_name.startswith(BLOCKED_MODEL_PREFIXES):
            raise ValueError(self.env._('Unknown or unavailable model "%s". Use find_models first.', model_name))
        Model = self.env[model_name]
        if Model._transient or Model._abstract:
            raise ValueError(self.env._('Model "%s" holds no records.', model_name))
        if tool.model_ids and model_name not in tool.model_ids.mapped('model'):
            raise ValueError(self.env._('This tool may not read "%s".', model_name))
        if not Model.has_access('read'):
            raise AccessError(self.env._('You are not allowed to read "%s".', model_name))
        return Model

    def _ai_fields_info(self, Model):
        """Fields the user may read (fields_get hides the others)."""
        info = Model.fields_get(attributes=['type', 'string', 'relation', 'selection'])
        return {name: value for name, value in info.items() if value['type'] not in SKIPPED_FIELD_TYPES}

    def _ai_domain(self, Model, filters):
        info = self._ai_fields_info(Model)
        domain = Domain.TRUE
        for item in filters or []:
            if not isinstance(item, dict):
                raise ValueError(self.env._('Each filter needs field, operator and value.'))
            path = str(item.get('field') or '')
            operator = str(item.get('operator') or '=').lower()
            value = item.get('value')
            if path.split('.')[0] not in info:
                raise ValueError(self.env._('Unknown field "%(field)s" on %(model)s.', field=path, model=Model._name))
            if operator not in OPERATORS:
                raise ValueError(self.env._('Operator "%s" is not allowed.', operator))
            if operator in ('in', 'not in') and not isinstance(value, list):
                value = [value]
            domain &= Domain(path, operator, value)
        return domain

    def _ai_pick_fields(self, Model, names):
        info = self._ai_fields_info(Model)
        if names:
            picked = [name for name in names if name in info]
        else:
            preferred = ['name', 'display_name', 'state', 'partner_id', 'email', 'phone', 'country_id', 'date',
                         'date_order', 'invoice_date', 'amount_total', 'list_price', 'qty_available', 'user_id',
                         'company_id', 'stage_id']
            picked = [name for name in preferred if name in info]
        return picked[:25]

    def _ai_format(self, records, field_names):
        rows = []
        for record in records:
            row = {'id': record.id, 'display_name': record.display_name}
            for name in field_names:
                field = record._fields[name]
                value = record[name]
                if field.type == 'many2one':
                    value = value.display_name or False
                elif field.type in ('one2many', 'many2many'):
                    value = {'count': len(value), 'first': value[:5].mapped('display_name')}
                elif field.type in ('date', 'datetime'):
                    value = fields.Datetime.to_string(value) if field.type == 'datetime' else fields.Date.to_string(value)
                elif field.type == 'html':
                    value = (value or '')[:500]
                elif field.type == 'selection':
                    value = dict(field._description_selection(self.env)).get(value, value)
                elif isinstance(value, str):
                    value = value[:500]
                row[name] = value
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Built-in read-only tools
    # ------------------------------------------------------------------
    def _ai_tool_find_models(self, tool, query=''):
        IrModel = self.env['ir.model'].sudo()
        domain = Domain('transient', '=', False)
        if query:
            domain &= Domain('name', 'ilike', query) | Domain('model', 'ilike', query)
        result = []
        for model in IrModel.search(domain, limit=200, order='model'):
            name = model.model
            if name not in self.env or name.startswith(BLOCKED_MODEL_PREFIXES) or self.env[name]._abstract:
                continue
            if tool.model_ids and model not in tool.model_ids:
                continue
            if self.env[name].has_access('read'):
                result.append({'model': name, 'name': model.name})
            if len(result) >= 25:
                break
        return {'models': result}

    def _ai_tool_model_fields(self, tool, model):
        Model = self._ai_get_model(tool, model)
        info = self._ai_fields_info(Model)
        fields_list = []
        for name, value in sorted(info.items()):
            entry = {'name': name, 'type': value['type'], 'label': value['string']}
            if value.get('relation'):
                entry['relation'] = value['relation']
            if value.get('selection'):
                entry['values'] = [key for key, _label in value['selection']][:20]
            fields_list.append(entry)
        return {'model': model, 'fields': fields_list[:200]}

    def _ai_tool_search_records(self, tool, model, filters=None, fields=None, limit=10, order=None):
        Model = self._ai_get_model(tool, model)
        domain = self._ai_domain(Model, filters)
        limit = max(1, min(int(limit or 10), MAX_LIMIT))
        if order:
            info = self._ai_fields_info(Model)
            name, _sep, direction = str(order).strip().partition(' ')
            stored = Model._fields.get(name)
            order = '%s %s' % (name, 'desc' if direction.lower() == 'desc' else 'asc') \
                if name in info and stored and stored.store else None
        records = Model.search(domain, limit=limit, order=order or None)
        total = Model.search_count(domain) if len(records) == limit else len(records)
        return {'model': model, 'total': total, 'records': self._ai_format(records, self._ai_pick_fields(Model, fields))}

    def _ai_tool_read_record(self, tool, model, record_id, fields=None):
        Model = self._ai_get_model(tool, model)
        record = Model.browse(int(record_id)).exists()
        if not record:
            raise MissingError(self.env._('Record %s not found.', record_id))
        record.check_access('read')
        return self._ai_format(record, self._ai_pick_fields(Model, fields))[0]

    def _ai_tool_count_records(self, tool, model, filters=None, group_by=None):
        Model = self._ai_get_model(tool, model)
        domain = self._ai_domain(Model, filters)
        if not group_by:
            return {'model': model, 'count': Model.search_count(domain)}
        info = self._ai_fields_info(Model)
        base = str(group_by).split(':')[0]
        if base not in info or not Model._fields[base]._description_groupable(self.env):
            raise ValueError(self.env._('Cannot group by "%s".', group_by))
        groups = Model._read_group(domain, [group_by], ['__count'], limit=MAX_LIMIT, order='__count desc')
        result = []
        for key, count in groups:
            if isinstance(key, models.BaseModel):
                key = key.display_name or False
            elif hasattr(key, 'isoformat'):
                key = key.isoformat()
            result.append({'group': key, 'count': count})
        return {'model': model, 'count': Model.search_count(domain), 'groups': result}
