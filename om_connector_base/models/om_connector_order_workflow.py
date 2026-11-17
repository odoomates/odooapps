import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class OmConnectorOrderWorkflow(models.Model):
    """ What Odoo does with an order imported from a shop or a marketplace: confirm it, invoice
    it, register its payment. A connector picks the workflow of an order, for example from its
    payment method. """
    _name = 'om.connector.order.workflow'
    _description = 'Imported Order Workflow'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    confirm_order = fields.Boolean(string='Confirm the Order', default=True)
    create_invoice = fields.Boolean(
        string='Create the Invoice', default=True,
        help="Invoices what can be invoiced: the products invoiced on ordered quantities. Products invoiced on "
             "delivered quantities are invoiced once delivered, as usual.")
    post_invoice = fields.Boolean(string='Post the Invoice', default=True)
    register_payment = fields.Boolean(
        string='Register the Payment', default=True,
        help="When the shop says the order is paid, registers its payment in the journal below.")
    journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', check_company=True,
        domain="[('type', 'in', ('bank', 'cash', 'credit'))]")
    invoice_date_is_order_date = fields.Boolean(
        string='Invoice on the Order Date',
        help="Dates the invoice and the payment on the date of the order, instead of today.")

    @api.constrains('register_payment', 'journal_id', 'post_invoice')
    def _check_journal(self):
        for workflow in self:
            if workflow.register_payment and (not workflow.journal_id or not workflow.post_invoice):
                raise ValidationError(_(
                    "To register the payments, %(workflow)s needs a payment journal and to post the invoices.",
                    workflow=workflow.name))

    def _connector_process(self, order, paid=False):
        """ Run the workflow on a sale order. ``paid``: the shop says the order is paid.
        Gives the posted or draft invoices made. """
        self.ensure_one()
        order.ensure_one()
        invoices = self.env['account.move']
        if self.confirm_order and order.state in ('draft', 'sent'):
            order.action_confirm()
        if order.state != 'sale' or not self.create_invoice:
            return invoices
        if order.invoice_status == 'to invoice':
            invoices = order._create_invoices()
            if self.invoice_date_is_order_date:
                invoices.write({'invoice_date': fields.Date.context_today(self, order.date_order)})
            if self.post_invoice:
                invoices.action_post()
        if paid and self.register_payment:
            self._connector_register_payment(order)
        return invoices

    def _connector_register_payment(self, order, amount=None, journal=None):
        """ Pay the open posted invoices of ``order``: all that is due, or ``amount``, in the payment
        journal of the workflow or in ``journal``. """
        self.ensure_one()
        invoices = order.invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.move_type == 'out_invoice'
            and m.payment_state != 'reversed' and not m.currency_id.is_zero(m.amount_residual))
        journal = journal or self.journal_id
        if not invoices or not journal:
            return self.env['account.payment']
        if amount is not None and order.currency_id.compare_amounts(amount, 0) <= 0:
            return self.env['account.payment']
        pending = self._connector_pending_payments(invoices)
        due = sum(invoices.mapped('amount_residual')) - pending
        if invoices[0].currency_id.compare_amounts(due, 0) <= 0:
            return self.env['account.payment']
        date = fields.Date.context_today(self, order.date_order) if self.invoice_date_is_order_date \
            else fields.Date.context_today(self)
        vals = {'journal_id': journal.id, 'payment_date': date, 'group_payment': True}
        if amount is not None or pending:
            vals['amount'] = due if amount is None else min(amount, due)
            vals['payment_difference_handling'] = 'open'
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoices.ids).create(vals)
        return wizard._create_payments()

    @api.model
    def _connector_pending_payments(self, invoices):
        """ Amount of the payments matched with ``invoices`` that have no journal entry (journals
        without an outstanding account): they do not lower the residual of the invoices. """
        payments = invoices.matched_payment_ids.filtered(
            lambda p: not p.move_id and p.state not in ('draft', 'canceled', 'rejected'))
        return sum(payments.mapped('amount'))

    def _connector_refund_payment(self, credit_note, amount=None, journal=None):
        """ Pay back a posted credit note: all of it, or ``amount``. """
        self.ensure_one()
        journal = journal or self.journal_id
        if credit_note.state != 'posted' or credit_note.payment_state not in ('not_paid', 'partial') or not journal:
            return self.env['account.payment']
        vals = {'journal_id': journal.id, 'payment_date': fields.Date.context_today(self)}
        if amount is not None:
            vals['amount'] = min(amount, credit_note.amount_residual)
            vals['payment_difference_handling'] = 'open'
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=credit_note.ids).create(vals)
        return wizard._create_payments()
