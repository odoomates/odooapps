# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from odoo.addons.account.tests.account_test_savepoint import AccountTestInvoicingCommon


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

    def test_asset_from_a_bill_line_with_a_long_label(self):
        """ A label longer than 32 characters, on several lines: the bill posts, the reference of the asset is the
        first line of the label. """
        label = '[FURN_6667] Acoustic Bloc Screens for the open space\nNoise-reducing panels, 3 m wide'
        bill = self.env['account.move'].create({
            'type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-15',
            'invoice_line_ids': [(0, 0, {
                'name': label,
                'quantity': 1.0,
                'price_unit': 1000.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [(6, 0, [])],
            })],
        })
        bill.action_post()
        asset = self.env['account.asset.asset'].search([('invoice_id', '=', bill.id)])
        self.assertEqual(asset.code, '[FURN_6667] Acoustic Bloc Screens for the open space')
        self.assertEqual(asset.name, label)
