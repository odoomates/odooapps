import base64
import binascii
import json
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError

from .om_mcp_server import INVALID_PARAMS, INVALID_REQUEST, McpError

RESOURCE_NOT_FOUND = -32002
PAGE_SIZE = 100
SCHEME = 'odoo://'
RECORD_URI = re.compile(r'^odoo://record/([a-z0-9_.]+)/(\d+)$')
MODEL_URI = re.compile(r'^odoo://model/([a-z0-9_.]+)$')
REPORTS_URI = re.compile(r'^odoo://reports/([a-z0-9_.]+)$')
REPORT_URI = re.compile(r'^odoo://report/([a-zA-Z0-9_.]+)/(\d+(?:,\d+)*)$')
ATTACHMENT_URI = re.compile(r'^odoo://attachment/(\d+)$')
SKIPPED_PREFIXES = ('message_', 'activity_', 'website_message_', 'rating_', 'has_message')
MAX_RECORD_FIELDS = 120


class OmMcpServer(models.AbstractModel):
    _inherit = 'om.mcp.server'

    @api.model
    def _mcp_dispatch(self, method, params, info):
        if method in ('resources/list', 'resources/templates/list', 'resources/read', 'prompts/list',
                      'prompts/get'):
            if params is not None and not isinstance(params, dict):
                raise McpError(INVALID_PARAMS, 'params must be an object')
            params = params or {}
            handler = {
                'resources/list': self._mcp_resources_list,
                'resources/templates/list': self._mcp_resource_templates,
                'resources/read': self._mcp_resources_read,
                'prompts/list': self._mcp_prompts_list,
                'prompts/get': self._mcp_prompts_get,
            }[method]
            return handler(params, info)
        return super()._mcp_dispatch(method, params, info)

    @api.model
    def _mcp_capabilities(self):
        # no stream of server messages is offered (GET answers 405), so the
        # server cannot announce changes: clients list again when they need to
        capabilities = super()._mcp_capabilities()
        capabilities.update({
            'resources': {'subscribe': False, 'listChanged': False},
            'prompts': {'listChanged': False},
        })
        return capabilities

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    @staticmethod
    def _mcp_page(items, params, key):
        cursor = params.get('cursor')
        offset = 0
        if cursor:
            try:
                offset = int(base64.urlsafe_b64decode(str(cursor).encode()).decode())
            except (ValueError, binascii.Error, UnicodeDecodeError):
                raise McpError(INVALID_PARAMS, 'Invalid cursor') from None
            if offset < 0 or offset > len(items):
                raise McpError(INVALID_PARAMS, 'Invalid cursor')
        page = items[offset:offset + PAGE_SIZE]
        result = {key: page}
        if offset + PAGE_SIZE < len(items):
            result['nextCursor'] = base64.urlsafe_b64encode(str(offset + PAGE_SIZE).encode()).decode()
        return result

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------
    @api.model
    def _mcp_readable_models(self):
        """Models the MCP permissions open and the user may read."""
        Tool = self.env['om.ai.tool']
        result = []
        for model_name, operations in sorted(self.env['om.mcp.model.access']._get_permissions().items()):
            if model_name not in self.env or not Tool._ai_model_allowed(model_name):
                continue
            Model = self.env[model_name]
            if Model._abstract or Model._transient or not Model.has_access('read'):
                continue
            result.append((model_name, operations))
        return result

    @api.model
    def _mcp_resources_list(self, params, info):
        _ = self.env._
        resources = [
            {'uri': 'odoo://context', 'name': 'context', 'title': _('Current user and company'),
             'description': _('The user who is connected, the companies, the time zone, the language and today.'),
             'mimeType': 'application/json'},
            {'uri': 'odoo://models', 'name': 'models', 'title': _('Available models'),
             'description': _('The models AI apps may use and what they may do on each one.'),
             'mimeType': 'application/json'},
        ]
        readable = self._mcp_readable_models()
        names = {model.model: model.name for model in self.env['ir.model'].sudo().search([
            ('model', 'in', [name for name, _ops in readable])])}
        for model_name, _operations in readable:
            resources.append({
                'uri': 'odoo://model/%s' % model_name,
                'name': model_name,
                'title': _('Fields of %s', names.get(model_name) or model_name),
                'description': _('Field names, types and labels of %s.', model_name),
                'mimeType': 'application/json',
            })
        return self._mcp_page(resources, params, 'resources')

    @api.model
    def _mcp_resource_templates(self, params, info):
        _ = self.env._
        templates = [
            {'uriTemplate': 'odoo://record/{model}/{id}', 'name': 'record', 'title': _('Record'),
             'description': _('The fields of one record, e.g. odoo://record/res.partner/7.'),
             'mimeType': 'application/json'},
            {'uriTemplate': 'odoo://model/{model}', 'name': 'model_fields', 'title': _('Fields of a model'),
             'description': _('Field names, types and labels of a model, e.g. odoo://model/sale.order.'),
             'mimeType': 'application/json'},
            {'uriTemplate': 'odoo://reports/{model}', 'name': 'reports', 'title': _('Reports of a model'),
             'description': _('The printable reports of a model, e.g. odoo://reports/sale.order.'),
             'mimeType': 'application/json'},
            {'uriTemplate': 'odoo://report/{report}/{ids}', 'name': 'report', 'title': _('Printed report'),
             'description': _('A report printed for records (PDF), e.g. odoo://report/sale.report_saleorder/12. '
                              'Several ids are separated by commas.'),
             'mimeType': 'application/pdf'},
            {'uriTemplate': 'odoo://attachment/{id}', 'name': 'attachment', 'title': _('Attachment'),
             'description': _('The content of an attached file.')},
        ]
        return self._mcp_page(templates, params, 'resourceTemplates')

    @api.model
    def _mcp_resources_read(self, params, info):
        uri = params.get('uri')
        if not isinstance(uri, str) or not uri.startswith(SCHEME) or len(uri) > 1000:
            raise McpError(INVALID_PARAMS, 'uri must be an odoo:// resource URI')
        info['target'] = uri[:200]
        try:
            content = self._mcp_read_uri(uri, info)
        except McpError:
            raise
        except AccessError as error:
            raise McpError(INVALID_REQUEST, str(error.args[0] if error.args else error), {'uri': uri},
                           status='denied') from None
        except (MissingError, ValueError, UserError) as error:
            raise McpError(RESOURCE_NOT_FOUND, 'Resource not found: %s' % (error.args[0] if error.args else uri),
                           {'uri': uri}, status='tool_error') from None
        content['uri'] = uri
        return {'contents': [content]}

    @api.model
    def _mcp_json(self, value):
        return {'mimeType': 'application/json', 'text': json.dumps(value, ensure_ascii=False, default=str, indent=1)}

    @api.model
    def _mcp_read_uri(self, uri, info):
        Tool = self.env['om.ai.tool']
        tool = Tool.browse()
        if uri == 'odoo://context':
            return self._mcp_json(Tool._ai_tool_current_user(tool))
        if uri == 'odoo://models':
            labels = {'read': 'read', 'create': 'create', 'write': 'write', 'unlink': 'delete',
                      'method': 'server actions'}
            return self._mcp_json({'models': [
                {'model': name, 'allowed': [labels[op] for op in labels if op in operations]}
                for name, operations in self._mcp_readable_models()]})
        match = MODEL_URI.match(uri)
        if match:
            info['model'] = match.group(1)
            return self._mcp_json(Tool._ai_tool_model_fields(tool, match.group(1)))
        match = RECORD_URI.match(uri)
        if match:
            info['model'] = match.group(1)
            return self._mcp_record(match.group(1), int(match.group(2)))
        match = REPORTS_URI.match(uri)
        if match:
            info['model'] = match.group(1)
            return self._mcp_json(self._mcp_reports(match.group(1)))
        match = REPORT_URI.match(uri)
        if match:
            return self._mcp_report(match.group(1), [int(i) for i in match.group(2).split(',')], info)
        match = ATTACHMENT_URI.match(uri)
        if match:
            return self._mcp_attachment(int(match.group(1)), info)
        raise McpError(RESOURCE_NOT_FOUND, 'Resource not found', {'uri': uri}, status='tool_error')

    @api.model
    def _mcp_record(self, model_name, record_id):
        Tool = self.env['om.ai.tool']
        Model = Tool._ai_get_model(Tool.browse(), model_name)
        record = Tool._ai_browse(Model, [record_id], 'read')
        # stored fields and lines: the computed helpers of the views are left out
        names = [name for name in sorted(Tool._ai_fields_info(Model))
                 if not name.startswith(SKIPPED_PREFIXES) and name not in ('id', 'display_name')
                 and 'token' not in name and 'password' not in name
                 and (Model._fields[name].store or Model._fields[name].type == 'one2many')]
        row = Tool._ai_format(record, names[:MAX_RECORD_FIELDS])[0]
        content = self._mcp_json({'model': model_name, 'record': row})
        if 'write_date' in record._fields and record.write_date:
            content['annotations'] = {'lastModified': fields.Datetime.to_datetime(record.write_date).strftime(
                '%Y-%m-%dT%H:%M:%SZ')}
        return content

    @api.model
    def _mcp_report_allowed(self, report):
        user = self.env.user
        return not report.group_ids or bool(report.group_ids & user.all_group_ids)

    @api.model
    def _mcp_reports(self, model_name):
        Tool = self.env['om.ai.tool']
        Tool._ai_get_model(Tool.browse(), model_name)
        reports = self.env['ir.actions.report'].sudo().search([
            ('model', '=', model_name), ('report_type', 'in', ('qweb-pdf', 'qweb-html'))])
        return {'model': model_name, 'reports': [
            {'report': report.report_name, 'name': report.name, 'type': report.report_type,
             'uri': 'odoo://report/%s/{ids}' % report.report_name}
            for report in reports if self._mcp_report_allowed(report)]}

    @api.model
    def _mcp_max_bytes(self):
        return max(1, self.env['ir.config_parameter'].sudo().get_int('om_ai_mcp.resource_max_kb', 10240)) * 1024

    @api.model
    def _mcp_report(self, report_name, ids, info):
        Tool = self.env['om.ai.tool']
        report = self.env['ir.actions.report'].sudo().search([
            ('report_name', '=', report_name), ('report_type', 'in', ('qweb-pdf', 'qweb-html'))], limit=1)
        if not report or not self._mcp_report_allowed(report):
            raise McpError(RESOURCE_NOT_FOUND, 'Report not found: %s' % report_name, status='tool_error')
        info['model'] = report.model
        Model = Tool._ai_get_model(Tool.browse(), report.model)
        records = Tool._ai_browse(Model, ids, 'read')
        Report = self.env['ir.actions.report'].with_context(report_pdf_no_attachment=True)
        if report.report_type == 'qweb-html':
            html, _type = Report._render_qweb_html(report.report_name, records.ids)
            return {'mimeType': 'text/html', 'text': html.decode() if isinstance(html, bytes) else str(html)}
        pdf, _type = Report._render_qweb_pdf(report.report_name, records.ids)
        if len(pdf) > self._mcp_max_bytes():
            raise McpError(INVALID_REQUEST, 'The report is larger than the limit of %s KB' % (
                self._mcp_max_bytes() // 1024), status='tool_error')
        return {'mimeType': 'application/pdf', 'blob': base64.b64encode(pdf).decode()}

    @api.model
    def _mcp_attachment(self, attachment_id, info):
        Tool = self.env['om.ai.tool']
        attachment = self.env['ir.attachment'].browse(attachment_id).exists()
        if not attachment:
            raise MissingError(self.env._('Attachment %s not found.', attachment_id))
        attachment.check_access('read')
        if not attachment.res_model:
            # files that belong to no record are not offered (assets, ...)
            raise MissingError(self.env._('Attachment %s not found.', attachment_id))
        info['model'] = attachment.res_model
        Tool._ai_get_model(Tool.browse(), attachment.res_model)
        if attachment.res_id:
            attachment.env[attachment.res_model].browse(attachment.res_id).check_access('read')
        if attachment.type == 'url':
            return {'mimeType': 'text/uri-list', 'text': attachment.url or ''}
        if attachment.file_size > self._mcp_max_bytes():
            raise McpError(INVALID_REQUEST, 'The file is larger than the limit of %s KB' % (
                self._mcp_max_bytes() // 1024), status='tool_error')
        mimetype = (attachment.mimetype or 'application/octet-stream').split(';')[0]
        raw = attachment.raw or b''
        if mimetype.startswith('text/') or mimetype in ('application/json', 'application/xml'):
            return {'mimeType': mimetype, 'text': raw.decode('utf-8', errors='replace')}
        return {'mimeType': mimetype, 'blob': base64.b64encode(raw).decode()}

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------
    @api.model
    def _mcp_get_prompts(self):
        """{name: prompt} of the templates offered to MCP clients; a template of
        the current company wins over a shared one with the same name."""
        prompts = self.env['om.ai.prompt'].search([
            ('mcp_available', '=', True), ('company_id', 'in', [self.env.company.id, False]),
        ], order='company_id, sequence, id')
        result = {}
        for prompt in prompts:
            result.setdefault(prompt._mcp_name(), prompt)
        return result

    @api.model
    def _mcp_prompts_list(self, params, info):
        items = []
        for name, prompt in self._mcp_get_prompts().items():
            spec = {
                'name': name,
                'description': prompt.mcp_description or prompt.name,
                'arguments': [{'name': arg, 'required': True} for arg in prompt._mcp_arguments()],
            }
            if info.get('protocol_version', '') >= '2025-06-18':
                spec['title'] = prompt.name
            items.append(spec)
        return self._mcp_page(items, params, 'prompts')

    @api.model
    def _mcp_prompts_get(self, params, info):
        name = params.get('name')
        if not isinstance(name, str) or not name:
            raise McpError(INVALID_PARAMS, 'name is required')
        info['target'] = name[:200]
        prompt = self._mcp_get_prompts().get(name)
        if not prompt:
            raise McpError(INVALID_PARAMS, 'Unknown prompt: %s' % name, status='tool_error')
        arguments = params.get('arguments') or {}
        if not isinstance(arguments, dict):
            raise McpError(INVALID_PARAMS, 'arguments must be an object')
        missing = [arg for arg in prompt._mcp_arguments() if arg not in arguments]
        if missing:
            raise McpError(INVALID_PARAMS, 'Missing arguments: %s' % ', '.join(missing), status='tool_error')
        values = {key: value if isinstance(value, str) else json.dumps(value) for key, value in arguments.items()}
        # MCP prompts know only user and assistant messages: the instructions
        # come first in the user message
        texts = [message['content'] for message in prompt._render(values) if message.get('content')]
        return {
            'description': prompt.mcp_description or prompt.name,
            'messages': [{'role': 'user', 'content': {'type': 'text', 'text': '\n\n'.join(texts)}}],
        }
