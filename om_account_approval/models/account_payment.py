from odoo import fields, models
from odoo.exceptions import UserError

METHOD = 'action_post'


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    om_approval_waiting = fields.Boolean(
        string='Waiting for Approval', compute='_compute_om_approval_waiting',
        search='_search_om_approval_waiting')

    def _compute_om_approval_waiting(self):
        waiting = set(self.env['approval.request'].sudo().search([
            ('res_model', '=', self._name), ('method', '=', METHOD), ('state', '=', 'to_approve'),
            ('res_id', 'in', self.ids),
        ]).mapped('res_id')) if self.ids else set()
        for payment in self:
            payment.om_approval_waiting = payment.id in waiting

    def _search_om_approval_waiting(self, operator, value):
        ids = self.env['approval.request'].sudo().search([
            ('res_model', '=', self._name), ('method', '=', METHOD), ('state', '=', 'to_approve'),
        ]).mapped('res_id')
        positive = (operator in ('=', 'in')) == bool(value)
        return [('id', 'in' if positive else 'not in', ids)]

    def action_post(self):
        """ The payments waiting for an approval are not posted, whatever posts them: the Confirm button, the
            Register Payment wizard, the recurring payments. """
        if self.env.context.get('om_approval_bypass'):
            return super().action_post()
        Request = self.env['approval.request']
        # the Register Payment wizard posts payments already marked paid, their journal entry still in draft
        to_post = self.filtered(lambda p: p.state == 'draft' or (p.move_id and p.move_id.state == 'draft'))
        blocked, released = Request._om_check_server(to_post, METHOD)
        if blocked:
            raise UserError(Request._om_blocked_message(blocked, METHOD))
        try:
            return super().action_post()
        finally:
            Request._restore_lock(released)
