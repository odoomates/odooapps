from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetDisposal(AccountTestInvoicingCommon):
    """ Selling or scrapping an asset takes it off the books with an entry of its own. """

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
        cls.gain_account = Account.create({
            'code': 'GAIN1', 'name': 'Gain on Disposal', 'account_type': 'income_other'})
        cls.loss_account = Account.create({
            'code': 'LOSS1', 'name': 'Loss on Disposal', 'account_type': 'expense'})
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Equipment',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': cls.asset_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.expense_account.id,
            'account_asset_gain_id': cls.gain_account.id,
            'account_asset_loss_id': cls.loss_account.id,
            'method_number': 12,
            'method_period': 1,
            'open_asset': True,
        })

    def _create_asset(self, **vals):
        asset = self.env['account.asset.asset'].create({
            'name': 'Laptop',
            'category_id': self.category.id,
            'value': 1200.0,
            'date': date(2025, 1, 1),
            'method': 'linear',
            'method_time': 'number',
            'method_number': 12,
            'method_period': 1,
            **vals,
        })
        asset.validate()
        return asset

    def _balances(self, move):
        balances = {}
        for line in move.line_ids:
            balances[line.account_id] = balances.get(line.account_id, 0.0) + line.balance
        return balances

    def _depreciate_all(self, asset):
        """ Post every scheduled depreciation, as the cron does over the life of the asset. """
        lines = asset.depreciation_line_ids.filtered(lambda line: not line.move_check)
        lines.create_move(post_move=True)
        asset.depreciation_line_ids.mapped('move_id').filtered(
            lambda move: move.state == 'draft').action_post()
        return asset

    # -------------------------------------------------------------------------
    # A fully depreciated asset is still on the books
    # -------------------------------------------------------------------------

    def test_fully_depreciated_asset_can_be_disposed(self):
        asset = self._depreciate_all(self._create_asset())
        self.assertEqual(asset.state, 'close')
        self.assertFalse(asset.disposal_date)
        self.assertEqual(asset.book_value, 0.0)

        asset.dispose(disposal_date=date(2025, 12, 31))

        self.assertEqual(asset.disposal_date, date(2025, 12, 31))
        self.assertEqual(asset.disposal_result, 0.0)
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -1200.0,
            self.accumulated_account: 1200.0,
        })

    def test_fully_depreciated_asset_sold_books_a_gain(self):
        asset = self._depreciate_all(self._create_asset())
        invoice = self.init_invoice('out_invoice', amounts=[150.0], taxes=[],
                                    invoice_date='2025-12-31', post=True)
        wizard = self.env['asset.sell'].with_context(
            active_model='account.asset.asset', active_id=asset.id).create({
                'action': 'sell',
                'date': date(2025, 12, 31),
                'sale_invoice_ids': [Command.set(invoice.ids)],
            })
        self.assertEqual(wizard.sale_amount, 150.0)
        wizard.action_confirm()

        self.assertEqual(asset.disposal_result, 150.0)
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -1200.0,
            self.accumulated_account: 1200.0,
            invoice.invoice_line_ids.account_id: 150.0,
            self.gain_account: -150.0,
        })

    # -------------------------------------------------------------------------
    # A running asset stops depreciating on the day it leaves
    # -------------------------------------------------------------------------

    def test_running_asset_disposed_writes_off_the_remainder(self):
        asset = self._create_asset()
        self.assertEqual(asset.state, 'open')

        asset.dispose(disposal_date=date(2025, 6, 30))

        self.assertEqual(asset.state, 'close')
        self.assertEqual(asset.disposal_date, date(2025, 6, 30))
        # the whole gross value left the asset account, nothing stayed behind
        balances = self._balances(asset.disposal_move_id)
        self.assertEqual(balances[self.asset_account], -1200.0)
        self.assertEqual(balances[self.accumulated_account], 1200.0)
        self.assertEqual(asset.disposal_result, 0.0)

    def test_salvage_value_is_the_loss_when_scrapped(self):
        asset = self._depreciate_all(self._create_asset(salvage_value=200.0))
        # 1000 depreciated, 200 of salvage value still carried
        self.assertEqual(asset.book_value, 200.0)

        asset.dispose(disposal_date=date(2025, 12, 31))

        self.assertEqual(asset.disposal_result, -200.0)
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -1200.0,
            self.accumulated_account: 1000.0,
            self.loss_account: 200.0,
        })

    # -------------------------------------------------------------------------
    # Guards
    # -------------------------------------------------------------------------

    def test_disposed_asset_cannot_be_disposed_again(self):
        asset = self._depreciate_all(self._create_asset())
        asset.dispose(disposal_date=date(2025, 12, 31))
        with self.assertRaises(UserError):
            asset.dispose(disposal_date=date(2025, 12, 31))

    def test_disposal_before_the_acquisition_is_refused(self):
        asset = self._create_asset()
        with self.assertRaises(UserError):
            asset.dispose(disposal_date=date(2024, 12, 31))

    def test_sale_without_an_invoice_is_refused(self):
        asset = self._depreciate_all(self._create_asset())
        wizard = self.env['asset.sell'].with_context(
            active_model='account.asset.asset', active_id=asset.id).create({
                'action': 'sell', 'date': date(2025, 12, 31)})
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_missing_gain_loss_account_is_reported(self):
        self.category.account_asset_loss_id = False
        asset = self._depreciate_all(self._create_asset(salvage_value=200.0))
        with self.assertRaises(UserError):
            asset.dispose(disposal_date=date(2025, 12, 31))
