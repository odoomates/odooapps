from odoo import api, fields, models
from odoo.exceptions import UserError


class FollowupSend(models.TransientModel):
    _inherit = 'followup.send'

    send_whatsapp = fields.Boolean(string='WhatsApp', compute='_compute_send_whatsapp', store=True, readonly=False)
    whatsapp_warning = fields.Char(compute='_compute_whatsapp_warning')

    @api.depends('level_id', 'partner_count')
    def _compute_send_whatsapp(self):
        for wizard in self:
            wizard.send_whatsapp = bool(wizard.level_id.send_whatsapp)

    @api.depends('partner_ids', 'send_whatsapp')
    def _compute_whatsapp_warning(self):
        for wizard in self:
            partners = wizard.partner_ids._origin
            missing = partners.browse()
            if wizard.send_whatsapp and partners:
                info = partners._phone_get_recipients_info()
                missing = partners.filtered(lambda p: not info[p.id]['sanitized'])
            wizard.whatsapp_warning = self.env._(
                "No valid mobile number for WhatsApp: %s", ', '.join(missing.mapped('display_name'))) if missing else False

    def action_send(self):
        self.ensure_one()
        if not self.send_whatsapp or self.send_email or self.print_letter:
            return super(FollowupSend, self.with_context(followup_send_whatsapp=self.send_whatsapp)).action_send()
        # WhatsApp only
        partners = self.partner_ids.filtered(lambda partner: not partner.followup_excluded)
        if not partners:
            raise UserError(self.env._('The customers are excluded from the follow-ups.'))
        single = len(self.partner_ids) == 1
        result = partners.with_context(followup_send_whatsapp=True)._followup_process(
            send_email=False, print_letter=False,
            levels={partner: self.level_id for partner in partners} if single and self.level_id else None,
        )
        missing = partners - result['whatsapp']
        message = self.env._('%(count)s reminder(s) sent by WhatsApp.', count=len(result['whatsapp']))
        if missing:
            message += ' ' + self.env._('Not sent: %s', ', '.join(missing.mapped('display_name')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'warning' if missing else 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
