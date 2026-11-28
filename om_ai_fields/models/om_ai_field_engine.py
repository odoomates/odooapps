import logging
import re

from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext

from odoo.addons.om_ai.models.om_ai_chat_job import markdown_to_html

_logger = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r'\{\{\s*([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\s*\}\}')
FILLABLE_TYPES = ('char', 'text', 'html', 'selection', 'many2one', 'boolean', 'float', 'integer', 'monetary')
HIDDEN_TYPES = ('binary', 'json', 'properties', 'properties_definition', 'reference', 'many2one_reference')
MAX_RELATED = 20
MAX_VALUE_CHARS = 4000
MAX_CANDIDATES = 200
SYSTEM_PROMPT = """You fill fields of a record in Odoo, a business application.
Answer with a JSON object only, with one key per field to fill, following the schema.
Use null for a field when the information given is not enough: never invent facts, numbers, names or prices.
For a field with a list of allowed values, answer with one of these values exactly.
Write texts in the language of the record values unless the instructions say otherwise."""


class OmAiFieldEngine(models.AbstractModel):
    """Fills fields of records with the AI: placeholders, JSON schema per
    field type, validation of the answer and writing of the values."""
    _name = 'om.ai.field.engine'
    _description = 'AI Fields Engine'

    # ------------------------------------------------------------------
    # Placeholders
    # ------------------------------------------------------------------
    @api.model
    def _placeholders(self, template):
        return list(dict.fromkeys(PLACEHOLDER.findall(template or '')))

    @api.model
    def _check_template(self, model_name, template):
        """Raise when a placeholder is not a path of fields of the model."""
        for path in self._placeholders(template):
            model = self.env[model_name]
            names = path.split('.')
            for index, name in enumerate(names):
                field = model._fields.get(name)
                if not field or field.type in HIDDEN_TYPES:
                    raise UserError(self.env._('"%(path)s" is not a field of %(model)s.',
                                               path=path, model=self.env['ir.model']._get(model_name).name))
                if index < len(names) - 1:
                    if not field.relational:
                        raise UserError(self.env._('"%(path)s": %(field)s has no sub-fields.',
                                                   path=path, field=name))
                    model = self.env[field.comodel_name]

    @api.model
    def _format_value(self, records, field):
        """Text of the value of ``field`` on ``records`` for a prompt."""
        values = []
        for record in records[:MAX_RELATED]:
            value = record[field.name]
            if field.type in ('many2one', 'one2many', 'many2many'):
                text = ', '.join(name for name in value[:MAX_RELATED].mapped('display_name') if name)
            elif field.type == 'selection':
                text = dict(field._description_selection(self.env)).get(value) or ''
            elif field.type == 'html':
                text = html2plaintext(value or '')
            elif field.type == 'boolean':
                text = self.env._('Yes') if value else self.env._('No')
            elif value is False or value is None:
                text = ''
            else:
                text = str(value)
            if text:
                values.append(text)
        return ', '.join(values)[:MAX_VALUE_CHARS]

    @api.model
    def _resolve(self, record, path):
        current = record
        names = path.split('.')
        for index, name in enumerate(names):
            field = current._fields.get(name)
            if not field or field.type in HIDDEN_TYPES or not current:
                return ''
            if not current._has_field_access(field, 'read'):
                return ''
            if index == len(names) - 1:
                return self._format_value(current, field)
            if not field.relational:
                return ''
            current = current[:MAX_RELATED].mapped(name)
        return ''

    @api.model
    def _render(self, record, template):
        """Replace {{ field.sub_field }} by the values of the record; nothing is evaluated."""
        return PLACEHOLDER.sub(lambda match: self._resolve(record, match.group(1)), template or '')

    # ------------------------------------------------------------------
    # Schema and validation
    # ------------------------------------------------------------------
    @api.model
    def _candidates(self, field, relation_domain=None):
        """Names of the records a many2one may take, or None when there are too many to list."""
        Comodel = self.env[field.comodel_name]
        domain = relation_domain or []
        records = Comodel.search(domain, limit=MAX_CANDIDATES + 1)
        if len(records) > MAX_CANDIDATES:
            return None
        return {record.display_name: record.id for record in records if record.display_name}

    @api.model
    def _field_schema(self, field, label, relation_domain=None):
        """JSON schema of one field and what is needed to read the answer back."""
        meta = {}
        if field.type == 'selection':
            selection = field._description_selection(self.env)
            meta['selection'] = selection
            schema = {
                'type': ['string', 'null'],
                'enum': [key for key, _label in selection] + [None],
                'description': '%s. Allowed values: %s' % (
                    label, '; '.join('%s = %s' % (key, value) for key, value in selection)),
            }
        elif field.type == 'many2one':
            candidates = self._candidates(field, relation_domain)
            meta['candidates'] = candidates
            schema = {'type': ['string', 'null'], 'description': '%s: the exact name of a %s' % (
                label, self.env['ir.model']._get(field.comodel_name).name)}
            if candidates is not None:
                schema['enum'] = list(candidates) + [None]
        elif field.type == 'boolean':
            schema = {'type': ['boolean', 'null'], 'description': label}
        elif field.type == 'integer':
            schema = {'type': ['integer', 'null'], 'description': label}
        elif field.type in ('float', 'monetary'):
            schema = {'type': ['number', 'null'], 'description': label}
        else:
            description = label
            if field.type == 'html':
                description += ' (plain text; lines starting with "- " become a list)'
            elif field.type == 'char':
                description += ' (one line)'
            schema = {'type': ['string', 'null'], 'description': description}
            if field.type == 'char' and getattr(field, 'size', None):
                schema['maxLength'] = field.size
        return schema, meta

    @api.model
    def _coerce(self, field, value, meta):
        """Return (ok, value to write). ok is False when the answer is not a valid value."""
        if value is None or value == '':
            return True, None
        ftype = field.type
        if ftype == 'selection':
            selection = meta.get('selection') or []
            for key, label in selection:
                if str(value).strip().lower() in (str(key).lower(), str(label).lower()):
                    return True, key
            return False, None
        if ftype == 'many2one':
            name = str(value).strip()
            candidates = meta.get('candidates')
            if candidates is not None:
                for candidate, record_id in candidates.items():
                    if candidate.lower() == name.lower():
                        return True, record_id
                return False, None
            Comodel = self.env[field.comodel_name]
            matches = Comodel.search([('display_name', '=ilike', name)], limit=2) \
                or Comodel.search([('display_name', 'ilike', name)], limit=2)
            if len(matches) == 1:
                return True, matches.id
            return False, None
        if ftype == 'boolean':
            if isinstance(value, bool):
                return True, value
            text = str(value).strip().lower()
            if text in ('true', 'yes', '1'):
                return True, True
            if text in ('false', 'no', '0'):
                return True, False
            return False, None
        if ftype in ('integer', 'float', 'monetary'):
            if isinstance(value, bool):
                return False, None
            try:
                number = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
            except (TypeError, ValueError):
                return False, None
            return True, int(round(number)) if ftype == 'integer' else number
        if not isinstance(value, (str, int, float)):
            return False, None
        text = str(value).strip()
        if ftype == 'char':
            text = ' '.join(text.split())
            if getattr(field, 'size', None):
                text = text[:field.size]
        elif ftype == 'html':
            text = markdown_to_html(text)
        return True, text

    @staticmethod
    def _is_empty(record, field):
        value = record[field.name]
        if field.type == 'html':
            return not html2plaintext(value or '').strip()
        if field.type in ('float', 'integer', 'monetary'):
            return not value
        return value is False or value is None or value == '' or (field.type == 'many2one' and not value)

    # ------------------------------------------------------------------
    # Filling
    # ------------------------------------------------------------------
    @api.model
    def _fill(self, records, field_records, prompt, instructions=None, purpose='fast', ai_model=None,
              overwrite=False, relation_domain=None):
        """Fill ``field_records`` (ir.model.fields) of ``records`` with the AI.

        :return: dict filled (record count), skipped, errors (list of texts)
        """
        result = {'filled': 0, 'skipped': 0, 'errors': []}
        if not records or not field_records:
            return result
        model_fields = [(records._fields[f.name], f) for f in field_records if f.name in records._fields]
        for record in records:
            targets = [(field, irf) for field, irf in model_fields if overwrite or self._is_empty(record, field)]
            if not targets:
                result['skipped'] += 1
                continue
            try:
                values, flags = self._ask(record, targets, prompt, instructions, purpose, ai_model,
                                          relation_domain)
            except (UserError, AccessError) as error:
                message = str(error.args[0] if error.args else error)
                result['errors'].append('%s: %s' % (record.display_name, message))
                if 'limit' in message.lower():
                    break
                continue
            if values:
                record.with_context(om_ai_fields_running=True).write(values)
                result['filled'] += 1
            else:
                result['skipped'] += 1
            if flags:
                result['errors'].append(self.env._('%(record)s: the AI gave no valid value for %(fields)s.',
                                                   record=record.display_name, fields=', '.join(flags)))
        return result

    @api.model
    def _ask(self, record, targets, prompt, instructions, purpose, ai_model, relation_domain=None):
        properties, metas, labels = {}, {}, {}
        for field, irf in targets:
            label = irf.field_description or field.string
            labels[field.name] = label
            domain = relation_domain if len(targets) == 1 else None
            properties[field.name], metas[field.name] = self._field_schema(field, label, domain)
        schema = {
            'type': 'object',
            'properties': properties,
            'required': list(properties),
            'additionalProperties': False,
        }
        system = SYSTEM_PROMPT
        if instructions:
            system += '\n\n' + instructions.strip()
        user_text = self._render(record, prompt)
        user_text += '\n\n' + self.env._('Fields to fill: %s', ', '.join(
            '%s (%s)' % (labels[name], name) for name in properties))
        # the administrator who set the AI field up allows it for every user who edits the records:
        # the call is logged under the user, within the user's and the company's limits
        answer = self.env['om.ai'].sudo()._ai_chat(
            [{'role': 'system', 'content': system}, {'role': 'user', 'content': user_text}],
            purpose=purpose or 'fast', model=ai_model or None, json_schema=schema, feature='fields',
        )
        data = answer.get('json')
        if not isinstance(data, dict):
            raise UserError(self.env._('The AI did not answer with the expected JSON object.'))
        values, flags = {}, []
        for field, _irf in targets:
            ok, value = self._coerce(field, data.get(field.name), metas[field.name])
            if not ok:
                flags.append(labels[field.name])
            elif value is not None:
                values[field.name] = value
        return values, flags

    @api.model
    def _notify_result(self, result, title=None):
        message = self.env._('%(filled)s record(s) filled, %(skipped)s unchanged.',
                             filled=result['filled'], skipped=result['skipped'])
        if result['errors']:
            message += '\n' + '\n'.join(result['errors'][:5])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title or self.env._('Fill with AI'),
                'message': message,
                'type': 'warning' if result['errors'] else 'success',
                'sticky': bool(result['errors']),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
