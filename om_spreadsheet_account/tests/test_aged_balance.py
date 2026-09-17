from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAgedBalance(AccountTestInvoicingCommon):
    """ The open items by age that the Receivables and Payables dashboard reads. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.Aged = cls.env['om.spreadsheet.aged.balance']

    def _invoice(self, move_type, amount, days_ago, partner=None):
        """ An invoice due `days_ago` days ago (in the future when negative) """
        date = self.today - relativedelta(days=days_ago)
        move = self.init_invoice(move_type, amounts=[amount], taxes=[], invoice_date=date, post=False,
                                 partner=partner or self.partner_a)
        move.invoice_payment_term_id = False
        move.invoice_date_due = date
        move.action_post()
        return move

    def _rows(self, move):
        return self.Aged.search([('move_id', '=', move.id)])

    def test_buckets(self):
        for days_ago, bucket in ((-10, 'not_due'), (0, 'not_due'), (1, '1_30'), (30, '1_30'), (31, '31_60'),
                                 (75, '61_90'), (120, 'over_90')):
            with self.subTest(days_ago=days_ago):
                row = self._rows(self._invoice('out_invoice', 100.0, days_ago))
                self.assertEqual(row.bucket, bucket)
                self.assertEqual(row.partner_type, 'customer')
                self.assertEqual(row.days_overdue, max(days_ago, 0))
                self.assertAlmostEqual(row.amount_residual, 100.0)

    def test_vendors_owed_are_positive(self):
        row = self._rows(self._invoice('in_invoice', 250.0, 45, partner=self.partner_b))
        self.assertEqual((row.partner_type, row.bucket), ('vendor', '31_60'))
        self.assertAlmostEqual(row.amount_residual, 250.0, msg='what is owed to the vendor reads positive')

    def test_paid_items_leave_the_view(self):
        invoice = self._invoice('out_invoice', 400.0, 5)
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({'amount': 150.0, 'payment_date': self.today})._create_payments()
        self.assertAlmostEqual(self._rows(invoice).amount_residual, 250.0, msg='the rest of a partial payment')
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({'payment_date': self.today})._create_payments()
        self.assertFalse(self._rows(invoice), 'a paid invoice is not open any more')

    def test_drafts_and_other_accounts_are_left_out(self):
        draft = self.init_invoice('out_invoice', amounts=[100.0], taxes=[], invoice_date=self.today)
        self.assertFalse(self._rows(draft))
        entry = self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'line_ids': [
                Command.create({'name': 'x', 'balance': 80.0, 'account_id': self.company_data['default_account_expense'].id,
                                'partner_id': self.partner_a.id}),
                Command.create({'name': 'x', 'balance': -80.0, 'account_id': self.company_data['default_account_revenue'].id,
                                'partner_id': self.partner_a.id}),
            ],
        })
        entry.action_post()
        self.assertFalse(self._rows(entry))

    def test_grouped_by_age(self):
        """ What the pivots of the dashboard ask for """
        self._invoice('out_invoice', 100.0, -5)
        self._invoice('out_invoice', 300.0, 40)
        groups = dict(self.Aged._read_group(
            [('partner_type', '=', 'customer'), ('partner_id', '=', self.partner_a.id)],
            ['bucket'], ['amount_residual:sum']))
        self.assertEqual(groups, {'not_due': 100.0, '31_60': 300.0})
