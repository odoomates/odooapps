from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.exceptions import UserError


def _last_month_end(wizard):
    return fields.Date.context_today(wizard) + relativedelta(day=1, days=-1)


class AccountLoanReclassify(models.TransientModel):
    _name = 'account.loan.reclassify'
    _description = 'Loan Current / Non-current Reclassification'

    date = fields.Date(
        string='Date', required=True, default=_last_month_end,
        help="The end of the period: the principal due within 12 months after it goes to the short-term account.")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    loan_ids = fields.Many2many(
        'account.loan', string='Loans', required=True,
        domain="[('company_id', '=', company_id), ('state', 'in', ('running', 'closed'))]",
        default=lambda self: self.env['account.loan'].search([
            ('company_id', '=', self.env.company.id), ('state', '=', 'running')]))

    def action_confirm(self):
        """ Post, per loan, the move between the long-term and the short-term accounts that leaves the
        principal due within 12 months on the short-term account. """
        self.ensure_one()
        moves = self.env['account.move']
        for loan in self.loan_ids:
            moves |= loan._reclassify(self.date)
        if not moves:
            raise UserError(self.env._('The short-term balances are right on %s: nothing to reclassify.', self.date))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Reclassifications'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }
