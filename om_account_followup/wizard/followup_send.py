from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FollowupSend(models.TransientModel):
    """ Send the reminder of one or several customers, with a preview of the email when there is one customer. """
    _name = 'followup.send'
    _description = 'Send Payment Reminder'

    partner_ids = fields.Many2many('res.partner', string='Customers', required=True)
    partner_count = fields.Integer(compute='_compute_partner_count')
    level_id = fields.Many2one(
        'followup.line', string='Reminder', compute='_compute_level', store=True, readonly=False,
        help='The level of the reminder sent. It follows the level due for the customer.')
    send_email = fields.Boolean(string='Email', compute='_compute_options', store=True, readonly=False)
    print_letter = fields.Boolean(string='Letter', compute='_compute_options', store=True, readonly=False)
    attach_invoices = fields.Boolean(
        string='Attach the Overdue Invoices', default=True,
        help='The PDF of the overdue invoices are attached to the email.')
    template_id = fields.Many2one(
        'mail.template', string='Email Template', compute='_compute_template', store=True, readonly=False,
        domain="[('model', '=', 'res.partner')]")
    recipient_ids = fields.Many2many(
        'res.partner', 'followup_send_recipient_rel', string='Recipients', compute='_compute_recipients',
        store=True, readonly=False)
    subject = fields.Char(compute='_compute_body', store=True, readonly=False)
    body = fields.Html(compute='_compute_body', store=True, readonly=False, sanitize_style=True)
    warning = fields.Char(compute='_compute_warning')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'partner_ids' in fields_list and not values.get('partner_ids') and \
                self.env.context.get('active_model') == 'res.partner':
            partners = self.env['res.partner'].browse(self.env.context.get('active_ids', [])).commercial_partner_id
            values['partner_ids'] = [(6, 0, partners.ids)]
        return values

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        for wizard in self:
            wizard.partner_count = len(wizard.partner_ids)

    @api.depends('partner_ids')
    def _compute_level(self):
        for wizard in self:
            partners = wizard.partner_ids._origin
            partner = partners[:1]
            wizard.level_id = (partner.followup_level_due_id or partner.latest_followup_level_id
                               or partner._followup_plan()._get_levels()[:1]) if len(partners) == 1 else False

    @api.depends('level_id', 'partner_count')
    def _compute_options(self):
        for wizard in self:
            level = wizard.level_id
            wizard.send_email = level.send_email if level else True
            wizard.print_letter = level.send_letter if level else False

    @api.depends('level_id')
    def _compute_template(self):
        default = self.env.ref('om_account_followup.email_template_om_account_followup_default',
                               raise_if_not_found=False)
        for wizard in self:
            wizard.template_id = wizard.level_id.email_template_id or default

    @api.depends('partner_ids')
    def _compute_recipients(self):
        for wizard in self:
            partners = wizard.partner_ids._origin
            wizard.recipient_ids = partners._followup_email_recipients() if len(partners) == 1 else False

    @api.depends('template_id', 'partner_ids')
    def _compute_body(self):
        for wizard in self:
            partner = wizard.partner_ids._origin
            if len(partner) != 1 or not wizard.template_id:
                wizard.subject = False
                wizard.body = False
                continue
            rendered = wizard.template_id.with_context(followup=True)._generate_template(
                partner.ids, ('subject', 'body_html'))[partner.id]
            wizard.subject = rendered.get('subject')
            wizard.body = rendered.get('body_html')

    @api.depends('partner_ids', 'send_email', 'recipient_ids')
    def _compute_warning(self):
        for wizard in self:
            warnings = []
            partners = wizard.partner_ids._origin
            excluded = partners.filtered('followup_excluded')
            if excluded:
                warnings.append(_('Excluded from the follow-ups: %s', ', '.join(excluded.mapped('display_name'))))
            if wizard.send_email:
                if len(partners) == 1:
                    missing = partners if not wizard.recipient_ids else self.env['res.partner']
                else:
                    missing = partners.filtered(lambda partner: not partner._followup_email_recipients())
                if missing:
                    warnings.append(_('No email address: %s', ', '.join(missing.mapped('display_name'))))
            wizard.warning = '\n'.join(warnings)

    def action_send(self):
        self.ensure_one()
        if not self.send_email and not self.print_letter:
            raise UserError(_('Choose to send an email, to print a letter, or both.'))
        partners = self.partner_ids.filtered(lambda partner: not partner.followup_excluded)
        if not partners:
            raise UserError(_('The customers are excluded from the follow-ups.'))
        single = len(self.partner_ids) == 1
        result = partners._followup_process(
            send_email=self.send_email,
            print_letter=self.print_letter,
            template=self.template_id,
            subject=self.subject if single else None,
            body=self.body if single else None,
            recipients=self.recipient_ids if single else None,
            attach_invoices=self.attach_invoices,
            levels={partner: self.level_id for partner in partners} if single and self.level_id else None,
        )
        if result['letters']:
            action = result['letters']._followup_statement_action()
            action['close_on_report_download'] = True
            return action
        message = _('%(count)s reminder(s) sent.', count=result['emails'])
        if result['unknown_emails']:
            message += ' ' + _('Not sent, without email address: %s',
                               ', '.join(result['unknown_emails'].mapped('display_name')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'warning' if result['unknown_emails'] else 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
