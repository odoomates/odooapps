from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_id = fields.Many2one('sale.order', copy=False, index='btree_not_null',
                                      readonly=True)
    subscription_period_start = fields.Date(string='Period Start', copy=False, readonly=True)
    subscription_period_end = fields.Date(string='Period End', copy=False, readonly=True)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get('subscription_skip_post_actions'):
            for move in posted.filtered(lambda m: m.subscription_id and m.move_type == 'out_invoice'):
                move.subscription_id.sudo()._subscription_after_invoice_post(move)
        return posted
