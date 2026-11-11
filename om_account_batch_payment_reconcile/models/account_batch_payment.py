from odoo import fields, models, _


class AccountBatchPayment(models.Model):
    _inherit = 'account.batch.payment'

    statement_line_ids = fields.Many2many(
        'account.bank.statement.line', compute='_compute_statement_line_ids', string='Bank Transactions')

    def _compute_statement_line_ids(self):
        for batch in self:
            batch.statement_line_ids = self.env['account.bank.statement.line'].search([
                ('om_batch_payment_ids', 'in', batch.payment_ids.ids),
            ]) if batch.payment_ids else False

    def action_open_statement_lines(self):
        self.ensure_one()
        return self.statement_line_ids._get_records_action(name=_('Bank Transactions of %s', self.name))
