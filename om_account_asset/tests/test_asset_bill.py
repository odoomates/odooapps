from datetime import date
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetBill(AccountTestInvoicingCommon):
    """ The lines of a vendor bill carrying an asset category create their assets on posting. """

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        Account = cls.env['account.account']
        cls.asset_account = Account.create({
            'code': 'ASSET1', 'name': 'Equipment',
            'user_type_id': cls.env.ref('account.data_account_type_fixed_assets').id})
        cls.accumulated_account = Account.create({
            'code': 'ASSET2', 'name': 'Accumulated Depreciation',
            'user_type_id': cls.env.ref('account.data_account_type_fixed_assets').id})
        cls.expense_account = Account.create({
            'code': 'EXPEN1', 'name': 'Depreciation Expense',
            'user_type_id': cls.env.ref('account.data_account_type_expenses').id})
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

    def _create_bill(self, move_type='in_invoice'):
        return self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner_a.id,
            'invoice_date': date(2025, 1, 15),
            'invoice_line_ids': [(0, 0, {
                'name': 'Laptop',
                'quantity': 1.0,
                'price_unit': 1000.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [(6, 0, [])],
            })],
        })

    def test_posted_bill_creates_its_assets(self):
        bill = self._create_bill()
        self.assertFalse(bill.asset_ids)
        bill.action_post()

        self.assertEqual(bill.asset_ids.category_id, self.category)
        self.assertEqual(bill.asset_ids.value, 1000.0)
        self.assertEqual(bill.asset_ids.date, date(2025, 1, 15))

    def test_asset_from_a_bill_line_with_a_long_label(self):
        """ A label longer than 32 characters, on several lines: the bill posts, the reference of the asset is the
        first line of the label. """
        label = '[FURN_6667] Acoustic Bloc Screens for the open space\nNoise-reducing panels, 3 m wide'
        bill = self._create_bill()
        bill.invoice_line_ids.name = label
        bill.action_post()
        self.assertEqual(bill.asset_ids.code, '[FURN_6667] Acoustic Bloc Screens for the open space')
        self.assertEqual(bill.asset_ids.name, label)

    def test_assets_from_auto_posted_bill(self):
        """ A bill posted on its date by the auto-post job creates its assets like a bill
        posted by hand. """
        bill = self._create_bill()
        bill.auto_post = True
        # the job commits outside of the test mode
        with patch.object(type(self.env.registry), 'in_test_mode', lambda registry: True):
            self.env['account.move']._autopost_draft_entries()

        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.asset_ids.category_id, self.category)
        self.assertEqual(bill.asset_ids.value, 1000.0)

    def test_refund_creates_no_asset(self):
        refund = self._create_bill(move_type='in_refund')
        refund.action_post()
        self.assertFalse(refund.asset_ids)
