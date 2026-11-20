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

    def test_lease_tour(self):
        """ Create a lease, confirm it and bill its first payment. """
        self.env.ref('base.user_admin').write({
            'company_id': self.env.company.id,
            'company_ids': [(4, self.env.company.id)],
        })
        self.lessor.name = 'Tour Lessor Properties'
        self.start_tour('/odoo/leases', 'om_account_loan_lease_tour', login='admin')
        lease = self.env['account.loan'].search([('partner_id', '=', self.lessor.id)])
        self.assertEqual((lease.loan_type, lease.state), ('lease', 'running'))
        # the present value of the payments (it depends on the days of the first period, from today)
        self.assertAlmostEqual(lease.principal, 11618.93, delta=60.0)
        self.assertEqual(lease.operation_ids.amount, lease.principal)
        first = lease.line_ids.sorted('sequence')[0]
        self.assertEqual(first.move_id.move_type, 'in_invoice')
        self.assertEqual(first.move_id.state, 'posted')
