from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetBill(AccountTestInvoicingCommon):
    """ The lines of a vendor bill carrying an asset category create their assets on posting. """

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

    def test_asset_from_a_bill_line_with_a_long_label(self):
        """ A label longer than 32 characters, on several lines: the bill posts, the reference of the asset is the
        first line of the label. """
        label = '[FURN_6667] Acoustic Bloc Screens for the open space\nNoise-reducing panels, 3 m wide'
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-15',
            'invoice_line_ids': [Command.create({
                'name': label,
                'price_unit': 1000.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [],
            })],
        })
        bill.action_post()
        self.assertEqual(bill.asset_ids.code, '[FURN_6667] Acoustic Bloc Screens for the open space')
        self.assertEqual(bill.asset_ids.name, label)

    def test_vendor_refund_creates_a_negative_asset(self):
        bill = self.env['account.move'].create({
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
        })
        bill.action_post()
        # the credit note is posted by hand, which creates the assets on 16
        refund = bill._reverse_moves([{'invoice_date': bill.invoice_date, 'date': bill.date}])
        refund.action_post()
        # the refund gives a negative asset, linked to the asset of the bill it refunds
        self.assertEqual(refund.asset_ids.value, -1000.0)
        self.assertEqual(refund.asset_ids.refunded_asset_id, bill.asset_ids)
        self.assertEqual(len(self.env['account.asset.asset'].search([('category_id', '=', self.category.id)])), 2)
