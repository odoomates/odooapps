from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


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
        'account.loan', string='Loans and Leases', required=True,
        domain="[('company_id', '=', company_id), ('state', 'in', ('running', 'closed'))]",
        default=lambda self: self.env['account.loan'].search([
            ('company_id', '=', self.env.company.id), ('state', '=', 'running')]))

    def action_confirm(self):
        """ Post, per loan, the move between the long-term and the short-term accounts that leaves the
        principal due within 12 months on the short-term account. """
        self.ensure_one()
        if self.date > fields.Date.context_today(self):
            raise UserError(self.env._(
                'Reclassify at the end of a period that is over: %s is in the future.',
                format_date(self.env, self.date)))
        loans = self.loan_ids.filtered(lambda loan: loan.company_id == self.company_id)
        not_running = loans.filtered(lambda loan: loan.state not in ('running', 'closed'))
        if not_running:
            raise UserError(self.env._(
                'Only running or closed loans are reclassified: %s.', ', '.join(not_running.mapped('display_name'))))
        moves = self.env['account.move']
        for loan in loans:
            moves |= loan._reclassify(self.date)
        if not moves:
            raise UserError(self.env._(
                'The short-term balances are right on %s: nothing to reclassify.', format_date(self.env, self.date)))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Reclassification'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
        }
