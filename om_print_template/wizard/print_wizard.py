from odoo import api, fields, models
from odoo.exceptions import UserError


class PrintWizard(models.TransientModel):
    """ Print a template for the records selected, from their Print menu. """
    _name = 'print.wizard'
    _description = 'Print a Template'

    res_model = fields.Char(required=True)
    res_ids = fields.Json(required=True)
    record_count = fields.Integer(compute='_compute_preview')
    template_id = fields.Many2one(
        'print.template', required=True,
        domain="[('model', '=', res_model)]")
    addressee = fields.Char(help='Leave as it is to use the addressee of the template.')
    preview = fields.Html(compute='_compute_preview', sanitize='email_outgoing')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        values.setdefault('res_model', context.get('active_model'))
        values.setdefault('res_ids', context.get('active_ids') or (
            [context['active_id']] if context.get('active_id') else []))
        return values

    @api.depends('template_id', 'res_ids')
    def _compute_preview(self):
        for wizard in self:
            wizard.record_count = len(wizard.res_ids or [])
            if wizard.template_id and wizard.res_ids:
                rendered = wizard.template_id._render_print_values(wizard.res_ids[:1])[wizard.res_ids[0]]
                wizard.preview = rendered['body_html']
            else:
                wizard.preview = False

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if self.template_id and self.res_ids:
            self.addressee = self.template_id._render_print_values(self.res_ids[:1])[self.res_ids[0]]['addressee']

    def _create_drafts(self):
        self.ensure_one()
        if not self.res_ids:
            raise UserError(self.env._('Select the records to print first.'))
        if self.template_id.model != self.res_model:
            raise UserError(self.env._('%s does not print these records.', self.template_id.name))
        self.env[self.res_model].browse(self.res_ids).check_access('read')
        Issue = self.env['print.issue']
        issues = Issue._create_from_template(self.template_id, self.res_ids)
        if len(self.res_ids) == 1 and self.addressee:
            issues.addressee = self.addressee
        return issues

    def action_issue(self):
        issues = self._create_drafts()
        issues.action_issue()
        if len(issues) == 1:
            return issues.action_download()
        return self.env.ref('om_print_template.action_report_print_issue').report_action(issues)

    def action_draft(self):
        issues = self._create_drafts()
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'print.issue',
            'name': self.env._('Draft Prints'),
        }
        if len(issues) == 1:
            return dict(action, view_mode='form', views=[(False, 'form')], res_id=issues.id)
        return dict(action, view_mode='list,form', domain=[('id', 'in', issues.ids)])
