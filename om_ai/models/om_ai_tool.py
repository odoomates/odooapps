import base64
import binascii
import json
import logging

import psycopg2
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.fields import Command, Domain

_logger = logging.getLogger(__name__)

BLOCKED_MODEL_PREFIXES = ('ir.', 'base.', 'bus.', 'om.ai.', 'res.users.apikeys', 'res.users.settings',
                          'res.users.log', 'res.device', 'auth.', 'mail.mail', 'iap.', 'payment.provider',
                          'fetchmail.', 'mail.alias')
OPERATORS = ('=', '!=', '>', '>=', '<', '<=', 'in', 'not in', 'ilike', 'not ilike', 'like', 'not like')
SKIPPED_FIELD_TYPES = ('binary', 'json', 'properties', 'properties_definition')
MAX_LIMIT = 50
MAX_GROUPS = 200
AGGREGATE_FUNCTIONS = ('sum', 'avg', 'min', 'max', 'count', 'count_distinct')
TEXT_MIMETYPES = ('application/json', 'application/xml', 'application/javascript', 'application/x-yaml',
                  'application/csv', 'application/sql')
IMAGE_MIMETYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')
MAX_TEXT_CHARS = 100000


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
    server_action_id = fields.Many2one(
        'ir.actions.server', string='Server Action', ondelete='cascade',
        help='Run this server action as the user. The arguments are in the context key ai_arguments, '
             'record_ids become the active records.')

    _code_unique = models.Constraint('UNIQUE(code)', 'The tool code must be unique.')

    @api.onchange('server_action_id')
    def _onchange_server_action_id(self):
        for tool in self.filtered('server_action_id'):
            tool.method = '_ai_tool_server_action'
            tool.read_only = False
            if not tool.description:
                tool.description = tool.server_action_id.name

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

    def _get_parameters(self):
        """JSON schema of the arguments of the tool."""
        self.ensure_one()
        tool = self.sudo()
        schema = json.loads(tool.parameters_schema)
        if tool.server_action_id.model_id:
            properties = schema.setdefault('properties', {})
            properties.setdefault('record_ids', {
                'type': 'array', 'items': {'type': 'integer'},
                'description': 'Ids of the %s records to run the action on' % tool.server_action_id.model_id.model,
            })
        return schema

    def _to_spec(self):
        """Tool definitions in the normalised format of the engine."""
        return [{
            'name': tool.code,
            'description': tool.description,
            'parameters': tool._get_parameters(),
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
        except psycopg2.IntegrityError as error:
            return {'error': self._ai_integrity_message(error)}

    def _ai_integrity_message(self, error):
        """Readable text of a database constraint error."""
        model = self.env['base']
        for model_class in self.env.registry.values():
            if error.diag.table_name == model_class._table:
                model = self.env[model_class._name]
                break
        return self.env._('The operation cannot be completed: %s', model._sql_error_to_message(error))

    # ------------------------------------------------------------------
    # Helpers for the built-in tools
    # ------------------------------------------------------------------
    def _ai_get_model(self, tool, model_name, operation='read'):
        """The model to work on, checked for the tool and the user.

        :param operation: read, create, write, unlink, post (chatter) or method (server actions)
        """
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
        self._ai_check_operation(Model, operation)
        if operation in ('create', 'write', 'unlink') and not Model.has_access(operation):
            raise AccessError(self.env._('You are not allowed to %(operation)s records of "%(model)s".',
                                         operation=operation, model=model_name))
        return Model

    def _ai_check_operation(self, Model, operation):
        """Hook for modules that limit what the tools may do on a model.
        Raise an AccessError to refuse. The access rights of the user always apply."""
        return True

    def _ai_model_allowed(self, model_name, operation='read'):
        """Whether :meth:`_ai_check_operation` lets the tools use the model."""
        try:
            self._ai_check_operation(self.env[model_name], operation)
        except AccessError:
            return False
        return True

    @api.model
    def _ai_batch_limit(self):
        """Most records a tool may create, change or delete in one call."""
        return max(1, self.env['ir.config_parameter'].sudo().get_int('om_ai.tool_batch_limit', 20))

    @api.model
    def _ai_attachment_limit(self):
        """Largest attachment (bytes) a tool may return or upload."""
        return max(1, self.env['ir.config_parameter'].sudo().get_int('om_ai.tool_attachment_kb', 1024)) * 1024

    def _ai_record_ids(self, record_ids):
        if isinstance(record_ids, (int, str)):
            record_ids = [record_ids]
        if not isinstance(record_ids, list) or not record_ids:
            raise ValueError(self.env._('Give the record ids as a list of integers.'))
        ids = list(dict.fromkeys(int(record_id) for record_id in record_ids))
        limit = self._ai_batch_limit()
        if len(ids) > limit:
            raise ValueError(self.env._('At most %s records per call.', limit))
        return ids

    def _ai_browse(self, Model, record_ids, operation='read'):
        ids = self._ai_record_ids(record_ids)
        records = Model.browse(ids).exists()
        missing = set(ids) - set(records.ids)
        if missing:
            raise MissingError(self.env._('Records not found: %s.', ', '.join(map(str, sorted(missing)))))
        records.check_access(operation)
        return records

    def _ai_values(self, Model, values, depth=0):
        """Turn simple values of the AI into ORM values. Relations take ids (or a name
        to look up), one2many lines take a list of value dicts."""
        if not isinstance(values, dict) or not values:
            raise ValueError(self.env._('Give the values as an object of field names and values.'))
        info = Model.fields_get(attributes=['type', 'readonly', 'relation', 'selection'])
        result = {}
        for name, value in values.items():
            field = Model._fields.get(name)
            if name not in info or not field or name in ('id', 'create_uid', 'create_date', 'write_uid',
                                                         'write_date', 'display_name'):
                raise ValueError(self.env._('Unknown field "%(field)s" on %(model)s.', field=name, model=Model._name))
            ftype = info[name]['type']
            if ftype in ('binary', 'properties', 'properties_definition') or \
                    (field.compute and not field.inverse and not field.store) or \
                    (field.compute and not field.store and field.readonly):
                raise ValueError(self.env._('The field "%s" cannot be set by a tool.', name))
            if ftype == 'many2one':
                value = self._ai_relation_id(info[name]['relation'], value)
            elif ftype in ('many2many', 'one2many'):
                value = self._ai_x2many(field, info[name]['relation'], value, depth)
            elif ftype == 'selection' and value not in (False, None):
                keys = {key: key for key, _label in info[name]['selection']}
                keys.update({str(label).lower(): key for key, label in info[name]['selection']})
                if value not in keys and str(value).lower() not in keys:
                    allowed = ', '.join(key for key, _label in info[name]['selection'])
                    raise ValueError(self.env._('"%(value)s" is not a value of %(field)s. Use one of: %(values)s',
                                                value=value, field=name, values=allowed))
                value = keys.get(value) or keys[str(value).lower()]
            result[name] = value
        return result

    def _ai_relation_id(self, relation, value):
        if value in (False, None, 0, ''):
            return False
        if isinstance(value, dict):
            value = value.get('id') or value.get('name')
        if isinstance(value, bool):
            raise ValueError(self.env._('Give an id or a name for a %s.', relation))
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            record = self.env[relation].browse(int(value)).exists()
            if not record:
                raise MissingError(self.env._('No %(model)s with id %(id)s.', model=relation, id=value))
            return record.id
        matches = self.env[relation].name_search(str(value), operator='=ilike', limit=2) or \
            self.env[relation].name_search(str(value), limit=2)
        if not matches:
            raise ValueError(self.env._('No record of %(model)s matches "%(name)s".', model=relation, name=value))
        if len(matches) > 1:
            raise ValueError(self.env._('Several records of %(model)s match "%(name)s": give an id.',
                                        model=relation, name=value))
        return matches[0][0]

    def _ai_x2many(self, field, relation, value, depth):
        if value in (False, None):
            return [Command.clear()]
        if not isinstance(value, list):
            value = [value]
        commands = []
        for item in value:
            if isinstance(item, dict) and field.type == 'one2many':
                if depth >= 1:
                    raise ValueError(self.env._('Lines inside lines are not supported.'))
                commands.append(Command.create(self._ai_values(self.env[relation], item, depth + 1)))
            else:
                record_id = self._ai_relation_id(relation, item)
                if record_id:
                    commands.append(Command.link(record_id))
        if field.type == 'many2many' and all(command[0] == Command.LINK for command in commands):
            return [Command.set([command[1] for command in commands])]
        return commands

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
            if self.env[name].has_access('read') and self._ai_model_allowed(name):
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

    @staticmethod
    def _ai_group_key(key):
        if isinstance(key, models.BaseModel):
            return {'id': key.id, 'name': key.display_name} if key else False
        if hasattr(key, 'isoformat'):
            return key.isoformat()
        return key

    def _ai_tool_aggregate_records(self, tool, model, filters=None, group_by=None, aggregates=None, order=None,
                                   limit=50):
        Model = self._ai_get_model(tool, model)
        domain = self._ai_domain(Model, filters)
        info = self._ai_fields_info(Model)
        if isinstance(group_by, str):
            group_by = [group_by]
        group_by = list(group_by or [])[:3]
        for spec in group_by:
            base = str(spec).split(':')[0]
            if base not in info or not Model._fields[base]._description_groupable(self.env):
                raise ValueError(self.env._('Cannot group by "%s".', spec))
        if isinstance(aggregates, str):
            aggregates = [aggregates]
        specs = ['__count']
        for spec in aggregates or []:
            name, _sep, function = str(spec).partition(':')
            function = function or 'sum'
            if name == '__count':
                continue
            if name not in info or not Model._fields[name].store:
                raise ValueError(self.env._('Cannot aggregate "%s": it must be a stored field you may read.', name))
            if function not in AGGREGATE_FUNCTIONS:
                raise ValueError(self.env._('Unknown aggregate "%(function)s". Use one of: %(functions)s',
                                            function=function, functions=', '.join(AGGREGATE_FUNCTIONS)))
            specs.append('%s:%s' % (name, function))
        order_spec = None
        if order and group_by:
            name, _sep, direction = str(order).strip().partition(' ')
            if name in specs or name in group_by:
                order_spec = '%s %s' % (name, 'desc' if direction.lower() == 'desc' else 'asc')
        limit = max(1, min(int(limit or 50), MAX_GROUPS))
        rows = Model._read_group(domain, group_by, specs, limit=limit if group_by else None, order=order_spec)
        result = []
        for row in rows:
            entry = {spec: self._ai_group_key(value) for spec, value in zip(group_by, row[:len(group_by)])}
            for spec, value in zip(specs, row[len(group_by):]):
                entry['count' if spec == '__count' else spec] = value
            result.append(entry)
        if not group_by:
            return {'model': model, 'totals': result[0] if result else {}}
        return {'model': model, 'groups': result, 'truncated': len(result) >= limit}

    # ------------------------------------------------------------------
    # Built-in tools that change data (the user confirms them)
    # ------------------------------------------------------------------
    def _ai_tool_create_records(self, tool, model, records=None, values=None):
        Model = self._ai_get_model(tool, model, 'create')
        if records is None and values is not None:
            records = [values]
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list) or not records:
            raise ValueError(self.env._('Give the records to create as a list of value objects.'))
        limit = self._ai_batch_limit()
        if len(records) > limit:
            raise ValueError(self.env._('At most %s records per call.', limit))
        created = Model.create([self._ai_values(Model, vals) for vals in records])
        return {'model': model, 'created': [{'id': rec.id, 'display_name': rec.display_name} for rec in created]}

    def _ai_tool_update_records(self, tool, model, record_ids, values):
        Model = self._ai_get_model(tool, model, 'write')
        records = self._ai_browse(Model, record_ids, 'write')
        records.write(self._ai_values(Model, values))
        return {'model': model, 'updated': [{'id': rec.id, 'display_name': rec.display_name} for rec in records]}

    def _ai_tool_delete_records(self, tool, model, record_ids):
        Model = self._ai_get_model(tool, model, 'unlink')
        records = self._ai_browse(Model, record_ids, 'unlink')
        deleted = [{'id': rec.id, 'display_name': rec.display_name} for rec in records]
        records.unlink()
        return {'model': model, 'deleted': deleted}

    def _ai_tool_post_message(self, tool, model, record_id, body, kind='note'):
        Model = self._ai_get_model(tool, model, 'post')
        if not hasattr(Model, 'message_post'):
            raise ValueError(self.env._('Records of "%s" have no chatter.', model))
        record = self._ai_browse(Model, [record_id], 'read')
        text = str(body or '').strip()
        if not text:
            raise ValueError(self.env._('The message is empty.'))
        html = Markup('<br/>').join(escape(line) for line in text.splitlines())
        message = record.message_post(
            body=html, message_type='comment',
            subtype_xmlid='mail.mt_comment' if kind == 'comment' else 'mail.mt_note')
        return {'model': model, 'record_id': record.id, 'message_id': message.id}

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------
    def _ai_attachment_info(self, attachment):
        return {
            'id': attachment.id,
            'name': attachment.name,
            'mimetype': attachment.mimetype,
            'size': attachment.file_size,
            'type': attachment.type,
            'create_date': fields.Datetime.to_string(attachment.create_date),
        }

    def _ai_tool_list_attachments(self, tool, model, record_id, limit=50):
        Model = self._ai_get_model(tool, model)
        record = self._ai_browse(Model, [record_id], 'read')
        attachments = self.env['ir.attachment'].search(
            [('res_model', '=', model), ('res_id', '=', record.id)],
            limit=max(1, min(int(limit or 50), 100)), order='id desc')
        return {'model': model, 'record_id': record.id,
                'attachments': [self._ai_attachment_info(att) for att in attachments]}

    def _ai_tool_read_attachment(self, tool, attachment_id):
        attachment = self.env['ir.attachment'].browse(int(attachment_id)).exists()
        if not attachment:
            raise MissingError(self.env._('Attachment %s not found.', attachment_id))
        attachment.check_access('read')
        if attachment.res_model:
            self._ai_get_model(tool, attachment.res_model)
        result = self._ai_attachment_info(attachment)
        if attachment.type == 'url':
            result['url'] = attachment.url
            return result
        if attachment.file_size > self._ai_attachment_limit():
            result['note'] = self.env._('The file is larger than the limit of %s KB; its content is not returned.',
                                        self._ai_attachment_limit() // 1024)
            return result
        mimetype = (attachment.mimetype or '').split(';')[0]
        if mimetype in IMAGE_MIMETYPES:
            result['image'] = {'mime_type': mimetype, 'data': base64.b64encode(attachment.raw or b'').decode()}
        elif mimetype.startswith('text/') or mimetype in TEXT_MIMETYPES:
            text = (attachment.raw or b'').decode('utf-8', errors='replace')
            result['text'] = text[:MAX_TEXT_CHARS]
            result['truncated'] = len(text) > MAX_TEXT_CHARS
        else:
            result['note'] = self.env._('Only text and image files are returned; this is %s.', mimetype or 'binary')
        return result

    def _ai_tool_upload_attachment(self, tool, model, record_id, name, data, mimetype=None):
        Model = self._ai_get_model(tool, model, 'write')
        record = self._ai_browse(Model, [record_id], 'write')
        try:
            raw = base64.b64decode(str(data or ''), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError(self.env._('The data must be base64 encoded.')) from None
        if not raw:
            raise ValueError(self.env._('The file is empty.'))
        if len(raw) > self._ai_attachment_limit():
            raise ValueError(self.env._('The file is larger than the limit of %s KB.',
                                        self._ai_attachment_limit() // 1024))
        vals = {'name': str(name or 'file'), 'raw': raw, 'res_model': model, 'res_id': record.id}
        if mimetype:
            vals['mimetype'] = str(mimetype)
        attachment = self.env['ir.attachment'].create(vals)
        return self._ai_attachment_info(attachment)

    # ------------------------------------------------------------------
    # Context and server actions
    # ------------------------------------------------------------------
    def _ai_tool_current_user(self, tool):
        user = self.env.user
        now = fields.Datetime.now()
        return {
            'user': {'id': user.id, 'name': user.name, 'login': user.login},
            'company': {'id': self.env.company.id, 'name': self.env.company.name},
            'active_companies': [{'id': company.id, 'name': company.name} for company in self.env.companies],
            'allowed_companies': [{'id': company.id, 'name': company.name} for company in user.company_ids],
            'tz': user.tz or 'UTC',
            'lang': user.lang,
            'now_utc': fields.Datetime.to_string(now),
            'today': fields.Date.to_string(fields.Date.context_today(self.with_context(tz=user.tz))),
        }

    def _ai_tool_server_action(self, tool, record_ids=None, **arguments):
        action = tool.sudo().server_action_id
        if not action:
            raise UserError(self.env._('The tool %s has no server action.', tool.code))
        context = {'ai_arguments': arguments, 'ai_tool': tool.code}
        model_name = action.model_id.model
        if model_name:
            Model = self._ai_get_model(tool, model_name, 'method')
            context['active_model'] = model_name
            if record_ids:
                records = self._ai_browse(Model, record_ids, 'read')
                context.update(active_ids=records.ids, active_id=records[:1].id)
        result = self.env['ir.actions.server'].browse(action.id).with_context(**context).run()
        if isinstance(result, dict) and result.get('type'):
            return {'done': True, 'action': {'type': result.get('type'), 'name': result.get('name')}}
        try:
            json.dumps(result)
        except (TypeError, ValueError):
            result = str(result)
        return {'done': True, 'result': result or False}
