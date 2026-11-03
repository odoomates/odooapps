from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .account_batch_payment import LOCKED_PAYMENT_FIELDS


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    batch_payment_id = fields.Many2one(
        'account.batch.payment', string='Batch', index='btree_not_null', copy=False, readonly=True,
        ondelete='set null', check_company=True)
    om_is_cleared = fields.Boolean(
        string='Cleared by the Bank', compute='_compute_om_is_cleared',
        help="The bank cleared the payment: its outstanding journal item is matched with a bank transaction or, "
             "for a payment without journal entry, it is reconciled.")

    @api.depends('is_matched', 'state', 'move_id')
    def _compute_om_is_cleared(self):
        for payment in self:
            # a payment is Reconciled as soon as its invoices are paid, before the bank clears it: only a payment without
            # journal entry is reconciled by the bank
            payment.om_is_cleared = payment.is_matched if payment.move_id else payment.state == 'reconciled'

    def write(self, vals):
        locked = LOCKED_PAYMENT_FIELDS.intersection(vals)
        if locked:
            for payment in self:
                batch = payment.batch_payment_id
                if not batch or batch.state == 'draft':
                    continue
                if any(payment._om_differs(fname, vals[fname]) for fname in locked):
                    raise UserError(_(
                        'The payment %(payment)s belongs to the batch %(batch)s, already sent to the bank: '
                        'set the batch back to draft to change it.',
                        payment=payment.display_name, batch=batch.name))
        if vals.get('batch_payment_id'):
            batch = self.env['account.batch.payment'].browse(vals['batch_payment_id'])
            if batch.state != 'draft':
                raise UserError(_(
                    'The batch %s is already sent to the bank: set it back to draft to add payments.', batch.name))
        res = super().write(vals)
        if 'batch_payment_id' in vals:
            self.batch_payment_id._om_check_payments()
        return res

    def _om_differs(self, fname, value):
        field = self._fields[fname]
        return field.convert_to_cache(value, self) != field.convert_to_cache(self[fname], self)

    def action_create_batch_payment(self):
        """ Batch the selected payments. """
        if not self:
            raise UserError(_('Select the payments to batch.'))
        if batched := self.filtered('batch_payment_id'):
            raise UserError(_('These payments are already in a batch: %s',
                              ', '.join(batched.mapped('display_name'))))
        if not_batchable := self.filtered(
                lambda payment: payment.state in ('canceled', 'rejected')
                or (payment.state != 'draft' and payment.om_is_cleared)):
            raise UserError(_('Only draft payments and payments not yet cleared by the bank can be batched: %s',
                              ', '.join(not_batchable.mapped('display_name'))))
        if len(self.journal_id) > 1 or self.journal_id.type != 'bank':
            raise UserError(_('The payments of a batch are paid with one bank journal.'))
        if len(set(self.mapped('payment_type'))) > 1:
            raise UserError(_('A batch either sends money or receives money, not both.'))
        if len(self.payment_method_line_id) > 1:
            raise UserError(_('The payments of a batch use the same payment method.'))
        batch = self.env['account.batch.payment'].create({
            'journal_id': self.journal_id.id,
            'batch_type': self[0].payment_type,
            'payment_method_line_id': self.payment_method_line_id.id,
        })
        self.batch_payment_id = batch
        return {
            'name': _('Batch Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.batch.payment',
            'res_id': batch.id,
            'views': [(False, 'form')],
        }
