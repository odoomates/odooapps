# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAccountAsset(AccountTestInvoicingCommon):
    """ The life of an asset: confirmed, depreciated entry by entry, then closed. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.asset_account = Account.create({
            'code': 'ASSET1', 'name': 'Vehicles', 'account_type': 'asset_fixed'})
        cls.accumulated_account = Account.create({
            'code': 'ASSET2', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        cls.expense_account = Account.create({
            'code': 'EXPEN1', 'name': 'Depreciation Expense', 'account_type': 'expense'})
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Vehicles',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': cls.asset_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.expense_account.id,
            'method_number': 5,
            'method_period': 12,
        })

    def _create_asset(self, **vals):
        return self.env['account.asset.asset'].create({
            'name': "CEO's Car",
            'category_id': self.category.id,
            'value': 10000.0,
            'date': date(2025, 1, 1),
            'method': 'linear',
            'method_time': 'number',
            'method_number': 5,
            'method_period': 12,
            **vals,
        })

    def test_asset_is_depreciated_over_its_life_then_closed(self):
        asset = self._create_asset()
        self.assertEqual(asset.state, 'draft')

        asset.validate()
        self.assertEqual(asset.state, 'open', 'a confirmed asset is running')

        asset.compute_depreciation_board()
        self.assertEqual(asset.method_number, len(asset.depreciation_line_ids),
                         'one depreciation line per depreciation')
        self.assertEqual(sum(asset.depreciation_line_ids.mapped('amount')), 10000.0,
                         'the board depreciates the whole gross value')

        for line in asset.depreciation_line_ids:
            line.create_move()
        self.assertEqual(len(asset.depreciation_line_ids), asset.entry_count,
                         'every line carries its entry')

        asset.depreciation_line_ids.mapped('move_id').filtered(
            lambda move: move.state == 'draft').action_post()
        self.assertEqual(asset.state, 'close',
                         'the asset is closed once its last depreciation is posted')
        self.assertEqual(asset.value_residual, 0.0)

    def test_modify_changes_the_number_of_depreciations(self):
        asset = self._create_asset()
        asset.validate()
        asset.compute_depreciation_board()

        wizard = self.env['asset.modify'].with_context(active_id=asset.id).create({
            'name': 'Test reason',
            'method_number': 10,
            'method_period': 12,
        })
        wizard.modify()

        self.assertEqual(asset.method_number, 10)
        self.assertEqual(len(asset.depreciation_line_ids), 10,
                         'the board is recomputed over the new duration')

    def test_modify_refuses_fewer_depreciations_than_entries(self):
        asset = self._create_asset()
        asset.validate()
        asset.compute_depreciation_board()
        asset.depreciation_line_ids[0].create_move()

        wizard = self.env['asset.modify'].with_context(active_id=asset.id).create({
            'name': 'Too short',
            'method_number': 1,
            'method_period': 12,
        })
        with self.assertRaises(UserError):
            wizard.modify()

    def test_the_wizard_posts_the_depreciation_due(self):
        asset = self._create_asset()
        asset.validate()
        asset.compute_depreciation_board()
        due = asset.depreciation_line_ids.filtered(
            lambda line: line.depreciation_date <= date(2025, 12, 31))
        self.assertTrue(due, 'the first depreciation falls in 2025')

        wizard = self.env['asset.depreciation.confirmation.wizard'].create({
            'date': date(2025, 12, 31)})
        wizard.with_context(asset_type='purchase').asset_compute()

        self.assertTrue(all(due.mapped('move_check')),
                        'the depreciation due on the date carries an entry')
        self.assertFalse(
            any(asset.depreciation_line_ids.filtered(
                lambda line: line.depreciation_date > date(2025, 12, 31)).mapped('move_check')),
            'the depreciation still to come is left alone')
