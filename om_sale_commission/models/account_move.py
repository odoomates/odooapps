from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_referrer_id = fields.Many2one(
        'res.partner', string='Referrer', index='btree_not_null', tracking=True, check_company=True,
        help='Reseller or partner who brought the sale: earns the reseller commission.')
    om_commission_statement_ids = fields.One2many(
        'om.commission.statement', 'move_id', string='Commission Statements')

    def _om_commission_paid_date(self):
        """Date at which the invoice was fully paid: the date of its last reconciliation."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable'))
        partials = lines.matched_debit_ids | lines.matched_credit_ids
        return max(partials.mapped('max_date'), default=False) or self.invoice_date
