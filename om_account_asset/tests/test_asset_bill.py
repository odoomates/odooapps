from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetBill(AccountTestInvoicingCommon):
    """ The assets of a vendor bill are created when it is posted, however it is posted. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.asset_account = Account.create({
            'code': 'ASSET1', 'name': 'Equipment', 'account_type': 'asset_fixed'})
        cls.accumulated_account = Account.create({
            'code': 'ASSET2', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        cls.expense_account = Account.create({
            'code': 'EXPEN1', 'name': 'Depreciation Expense', 'account_type': 'expense'})
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Equipment',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': cls.asset_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.expense_account.id,
            'method_number': 12,
            'method_period': 1,
        })

    def _create_bill(self, **values):
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-01',
            'invoice_line_ids': [Command.create({
                'name': 'Laptop',
                'price_unit': 1000.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [],
            })],
            **values,
        })

    def test_assets_from_posted_bill(self):
        bill = self._create_bill()
        bill.action_post()
        self.assertEqual(bill.asset_ids.category_id, self.category)
        self.assertEqual(bill.asset_ids.value, 1000.0)

    def test_assets_from_auto_posted_bill(self):
        """ A bill posted on its date by the auto-post job creates its assets like a bill posted by hand """
        bill = self._create_bill(auto_post='at_date', date='2025-01-31')
        with freeze_time('2025-01-31'):
            self.env['account.move']._autopost_draft_entries()

        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.asset_ids.category_id, self.category)
        self.assertEqual(bill.asset_ids.value, 1000.0)

    def test_credit_note_creates_no_asset(self):
        bill = self._create_bill()
        bill.action_post()
        refund = bill._reverse_moves([{'invoice_date': bill.invoice_date, 'date': bill.date}], cancel=True)
        self.assertEqual(refund.state, 'posted')
        self.assertFalse(refund.asset_ids)
        self.assertEqual(len(self.env['account.asset.asset'].search([('category_id', '=', self.category.id)])), 1)
