from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval, time


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

    @api.depends('model')
    def _compute_render_model(self):
        for template in self:
            template.render_model = template.model

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
