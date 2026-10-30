from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetFromBill(AccountTestInvoicingCommon):
    """ A vendor bill posted creates the assets of its lines with an asset category. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Furniture',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': Account.create({
                'code': 'ASSETF1', 'name': 'Furniture', 'account_type': 'asset_fixed'}).id,
            'account_depreciation_id': Account.create({
                'code': 'ASSETF2', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'}).id,
            'account_depreciation_expense_id': Account.create({
                'code': 'EXPENF1', 'name': 'Depreciation Expense', 'account_type': 'expense'}).id,
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
                'quantity': 1,
                'price_unit': 1200.0,
                'tax_ids': [Command.clear()],
                'asset_category_id': self.category.id,
            })],
        })
        bill.action_post()
        self.assertEqual(bill.asset_ids.code, '[FURN_6667] Acoustic Bloc Screens for the open space')
        self.assertEqual(bill.asset_ids.name, label)
