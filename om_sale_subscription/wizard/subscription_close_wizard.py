from odoo import fields, models


class OmSubscriptionCloseWizard(models.TransientModel):
    _name = 'om.subscription.close.wizard'
    _description = 'Close Subscriptions'

    order_ids = fields.Many2many('sale.order', string='Subscriptions', required=True)
    close_reason_id = fields.Many2one('om.subscription.close.reason', string='Reason', required=True)
    note = fields.Text()
    send_mail = fields.Boolean(string='Inform the Customer', default=True)

    def action_close(self):
        self.ensure_one()
        self.order_ids._subscription_check_state(('progress', 'paused'))
        self.order_ids._subscription_close(reason=self.close_reason_id, note=self.note, send_mail=self.send_mail)
        return {'type': 'ir.actions.act_window_close'}
