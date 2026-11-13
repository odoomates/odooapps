import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval, time

# the fields of the body: {{ object.partner_id.name }}
EXPRESSION = re.compile(r'\{\{\s*(.+?)\s*\}\}')
# the formatting of WhatsApp: *bold*, _italic_, ~strikethrough~
FORMATS = [(re.compile(r'\*([^*\n]+)\*'), 'b'), (re.compile(r'(?<!\w)_([^_\n]+)_(?!\w)'), 'i'),
           (re.compile(r'~([^~\n]+)~'), 's')]


class OmWhatsappTemplate(models.Model):
    """ Text of a WhatsApp message for one kind of document. The body is an
    inline template (``{{ object.name }}``); the report, when set, is attached
    as a PDF for providers that send files. A provider that needs templates
    approved upstream links them to its account. """
    _name = 'om.whatsapp.template'
    _inherit = ['mail.render.mixin']
    _description = 'WhatsApp Template'
    _order = 'name, id'

    _unrestricted_rendering = True

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if 'model_id' in fields and not res.get('model_id') and res.get('model'):
            res['model_id'] = self.env['ir.model']._get(res['model']).id
        return res

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', string='Applies to', required=True, ondelete='cascade',
        domain=[('is_mail_thread', '=', True), ('transient', '=', False)])
    model = fields.Char(related='model_id.model', index=True, store=True)
    body = fields.Text(required=True, translate=True)
    report_id = fields.Many2one(
        'ir.actions.report', string='Attach Report', domain="[('model', '=', model)]",
        help="Printed as a PDF and sent with the message, by the providers that send files.")
    account_id = fields.Many2one(
        'om.whatsapp.account', string='Account', index='btree_not_null',
        help="Only offered when sending from this account. Leave empty to use it with every account.")
    company_id = fields.Many2one('res.company', related='account_id.company_id', store=True)
    sidebar_action_id = fields.Many2one('ir.actions.act_window', readonly=True, copy=False)
    preview = fields.Html(compute='_compute_preview', sanitize=False)

    @api.depends('model')
    def _compute_render_model(self):
        for template in self:
            template.render_model = template.model

    @api.depends('body', 'report_id', 'model')
    def _compute_preview(self):
        for template in self:
            template.preview = template._om_whatsapp_preview_html() if template.body else False

    def unlink(self):
        self.sudo().sidebar_action_id.unlink()
        return super().unlink()

    def action_create_sidebar_action(self):
        view = self.env.ref('om_whatsapp_base.om_whatsapp_composer_view_form')
        for template in self.filtered(lambda t: not t.sidebar_action_id):
            template.sidebar_action_id = self.env['ir.actions.act_window'].sudo().create({
                'name': _('Send WhatsApp (%s)', template.name),
                'res_model': 'om.whatsapp.composer',
                'context': "{'default_template_id': %d}" % template.id,
                'view_mode': 'form',
                'view_id': view.id,
                'target': 'new',
                'binding_model_id': template.model_id.id,
            })

    def action_unlink_sidebar_action(self):
        self.sudo().sidebar_action_id.unlink()

    # ------------------------------------------------------------
    # RENDERING
    # ------------------------------------------------------------

    def _om_whatsapp_render_body(self, res_ids):
        self.ensure_one()
        return self._render_field('body', res_ids, compute_lang=True)

    def _om_whatsapp_preview_html(self):
        """ The message as the customer sees it in WhatsApp: the PDF of the
        report at the top, the text with the values of a document and its
        formatting, then what a provider adds below it. """
        self.ensure_one()
        expressions = list(dict.fromkeys(EXPRESSION.findall(self.body or '')))
        values = self._om_whatsapp_preview_values(expressions)
        # the formatting first, on the whole text: *{{ object.name }}* makes the value bold
        html = str(escape(EXPRESSION.sub(lambda match: '\x00%d\x00' % expressions.index(match.group(1)), self.body or '')))
        for pattern, tag in FORMATS:
            html = pattern.sub(r'<%s>\1</%s>' % (tag, tag), html)

        def value(match):
            expression = expressions[int(match.group(1))]
            return str(Markup('<span class="o_om_whatsapp_preview_value" title="%s">%s</span>') % (
                expression, values.get(expression) or '{{ %s }}' % expression))

        body = Markup(re.sub(r'\x00(\d+)\x00', value, html.replace('\n', '<br/>')))
        header = Markup()
        if self.report_id:
            header = Markup(
                '<div class="o_om_whatsapp_preview_document"><span class="o_om_whatsapp_preview_pdf">PDF</span>'
                '<span>%s.pdf</span></div>') % (self.report_id.name or _("Document"))
        return Markup(
            '<div class="o_om_whatsapp_preview"><div class="o_om_whatsapp_preview_bubble">%s'
            '<div class="o_om_whatsapp_preview_text">%s</div>%s<div class="o_om_whatsapp_preview_time">12:00</div>'
            '</div></div>') % (header, body, self._om_whatsapp_preview_footer())

    def _om_whatsapp_preview_values(self, expressions):
        """ The value of each field of the body, from a document of the
        kind of the template. """
        self.ensure_one()
        record = self.env[self.model].search([], limit=1) if expressions and self.model in self.env else None
        values = {}
        for expression in expressions:
            try:
                rendered = record and self._render_template(
                    '{{ %s }}' % expression, record._name, record.ids, engine='inline_template')
                values[expression] = rendered and (rendered.get(record.id) or '').strip()
            except Exception:  # noqa: BLE001 - a field still being typed: shown as written
                values[expression] = False
        return values

    def _om_whatsapp_preview_footer(self):
        """ What a provider shows under the text: nothing by default. """
        return Markup()

    def _om_whatsapp_render_report(self, res_id):
        """ Return the (filename, content) of the report for one record, or
        None when the template has no report. """
        self.ensure_one()
        report = self.report_id
        if not report:
            return None
        content, report_format = self.env['ir.actions.report']._render_qweb_pdf(report, [res_id])
        name = _('Report')
        if report.print_report_name:
            name = safe_eval(report.print_report_name, {'object': self.env[self.model].browse(res_id), 'time': time})
        extension = f'.{report_format}'
        if not name.endswith(extension):
            name += extension
        return name, content
