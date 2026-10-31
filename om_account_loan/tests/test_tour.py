from odoo.tests import HttpCase, tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanTour(LoanCommon, HttpCase):

    def test_loan_tour(self):
        """ Create a loan, confirm it, draw it down, compute the schedule and pay the first instalment. """
        self.env.ref('base.user_admin').write({
            'company_id': self.env.company.id,
            'company_ids': [(4, self.env.company.id)],
        })
        self.lender.name = 'Tour Lending Bank'
        self.start_tour('/odoo/loans', 'om_account_loan_tour', login='admin')
        loan = self.env['account.loan'].search([('partner_id', '=', self.lender.id)])
        self.assertEqual(loan.state, 'running')
        self.assertEqual(loan.principal, 24000.0)
        self.assertEqual(loan.drawn_amount, 24000.0)
        self.assertEqual(len(loan.line_ids), 24)
        first = loan.line_ids.sorted('sequence')[0]
        self.assertEqual(first.state, 'posted')
        self.assertEqual(first.move_id.journal_id, self.bank_journal)
        self.assertEqual(loan.outstanding_amount, 24000.0 - first.principal)
