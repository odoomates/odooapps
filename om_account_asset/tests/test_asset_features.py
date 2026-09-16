from datetime import date

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetFeatures(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.asset_account = Account.create({'code': '151100', 'name': 'Equipment', 'account_type': 'asset_fixed'})
        cls.accumulated_account = Account.create({'code': '151900', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        cls.expense_account = Account.create({'code': '681100', 'name': 'Depreciation Expense', 'account_type': 'expense_depreciation'})
        cls.gain_account = Account.create({'code': '771100', 'name': 'Gain on Asset Sale', 'account_type': 'income_other'})
        cls.loss_account = Account.create({'code': '671100', 'name': 'Loss on Asset Disposal', 'account_type': 'expense'})
        cls.counterpart_account = Account.create({'code': '106100', 'name': 'Revaluation Reserve', 'account_type': 'equity'})
        cls.env.company.write({
            'asset_gain_account_id': cls.gain_account.id,
            'asset_loss_account_id': cls.loss_account.id,
        })
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Equipment',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': cls.asset_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.expense_account.id,
            'method_number': 12,
            'method_period': 1,
            'date_first_depreciation': 'last_day_period',
            'open_asset': True,
        })

    def _create_asset(self, validate_on='2024-12-15', **vals):
        asset = self.env['account.asset.asset'].create({
            'name': 'Laptop',
            'category_id': self.category.id,
            'value': 1200.0,
            'date': date(2025, 1, 1),
            'method': 'linear',
            'method_time': 'number',
            'method_number': 12,
            'method_period': 1,
            'date_first_depreciation': 'last_day_period',
            **vals,
        })
        if validate_on:
            with freeze_time(validate_on):
                asset.validate()
        return asset

    def _autopost(self, until):
        """ What the auto-post job does on `until`. """
        with freeze_time(until):
            self.env['account.move'].search([
                ('state', '=', 'draft'), ('auto_post', '!=', 'no'), ('date', '<=', until),
            ])._post()

    def _board(self, asset):
        return asset._get_board_moves().sorted(lambda m: (m.date, m.id))

    def _drafts(self, asset):
        return self._board(asset).filtered(lambda m: m.state == 'draft')

    def _balances(self, move):
        balances = {}
        for line in move.line_ids:
            balances[line.account_id] = balances.get(line.account_id, 0.0) + line.balance
        return balances

    # -------------------------------------------------------------------------
    # Board computation
    # -------------------------------------------------------------------------

    def test_linear_board(self):
        asset = self._create_asset()
        board = self._board(asset)
        self.assertEqual(board.mapped('asset_depreciation_amount'), [100.0] * 12)
        self.assertEqual(board.mapped('state'), ['draft'] * 12)
        self.assertEqual(set(board.mapped('auto_post')), {'at_date'})
        self.assertEqual(board[0].date, date(2025, 1, 31))
        self.assertEqual(board[1].date, date(2025, 2, 28))
        self.assertEqual(board[-1].date, date(2025, 12, 31))
        self.assertEqual(board[0].asset_depreciable_value, 1100.0)
        self.assertEqual(board[-1].asset_cumulative_depreciation, 1200.0)
        self.assertEqual(board[-1].asset_depreciable_value, 0.0)
        self.assertEqual(self._balances(board[0]), {self.accumulated_account: -100.0, self.expense_account: 100.0})

    def test_prorata_board(self):
        asset = self._create_asset(date=date(2025, 1, 15), prorata=True)
        amounts = self._board(asset).mapped('asset_depreciation_amount')
        # 17 days of January 2025, 11 months, then the 14 days left in January 2026
        self.assertEqual(amounts, [54.84] + [100.0] * 11 + [45.16])
        self.assertEqual(self._board(asset)[-1].date, date(2026, 1, 31))

    def test_confirm_posts_past_entries(self):
        asset = self._create_asset(validate_on='2025-03-15')
        board = self._board(asset)
        self.assertEqual(board.mapped('state'), ['posted'] * 2 + ['draft'] * 10)
        self.assertEqual(asset.value_residual, 1000.0)

    def test_autopost_closes_asset(self):
        asset = self._create_asset()
        self._autopost('2025-11-30')
        self.assertEqual(asset.state, 'open')
        self._autopost('2025-12-31')
        self.assertEqual(asset.state, 'close')
        self.assertEqual(asset.value_residual, 0.0)

    def test_rate_board(self):
        asset = self._create_asset(value=1000.0, method_time='rate', method_rate=30.0, method_period=12)
        board = self._board(asset)
        self.assertEqual(board.mapped('asset_depreciation_amount'), [300.0, 300.0, 300.0, 100.0])
        self.assertEqual(board.mapped('date'),
                         [date(2025, 12, 31), date(2026, 12, 31), date(2027, 12, 31), date(2028, 12, 31)])

    def test_degressive_then_linear_board(self):
        asset = self._create_asset(value=1000.0, method='degressive_then_linear', method_progress_factor=0.4,
                                   method_number=4, method_period=12)
        # degressive 400, 240, then linear once residual / remaining periods is higher: 360 / 2
        self.assertEqual(self._board(asset).mapped('asset_depreciation_amount'), [400.0, 240.0, 180.0, 180.0])

    def test_already_depreciated_amount_import(self):
        asset = self._create_asset(opening_depreciation=250.0)
        self.assertEqual(asset.value_residual, 950.0)
        board = self._board(asset)
        self.assertEqual(board.mapped('asset_depreciation_amount'), [50.0] + [100.0] * 9)
        self.assertEqual(board[0].date, date(2025, 3, 31))
        self.assertEqual(board[0].asset_cumulative_depreciation, 300.0)
        self.assertEqual(board[0].asset_depreciable_value, 900.0)

    def test_draft_asset_preview(self):
        asset = self._create_asset(validate_on=False)
        asset.compute_depreciation_board()
        board = self._board(asset)
        self.assertEqual(len(board), 12)
        self.assertEqual(set(board.mapped('auto_post')), {'no'})
        with self.assertRaises(UserError):
            board[0]._post()
        asset.method_number = 6
        self.assertEqual(self._board(asset).mapped('asset_depreciation_amount'), [200.0] * 6)
        with freeze_time('2025-02-15'):
            asset.validate()
        self.assertEqual(self._board(asset).mapped('state'), ['posted'] + ['draft'] * 5)

    def test_edit_draft_amount(self):
        asset = self._create_asset()
        january = self._board(asset)[0]
        asset.write({'depreciation_move_ids': [Command.update(january.id, {'asset_depreciation_amount': 150.0})]})

        self.assertEqual(self._balances(january), {self.accumulated_account: -150.0, self.expense_account: 150.0})
        board = self._board(asset)
        self.assertEqual(len(board), 12)
        self.assertAlmostEqual(sum(board.mapped('asset_depreciation_amount')), 1200.0)
        self.assertEqual(board[1].asset_depreciation_amount, 95.45)
        self.assertEqual(board[-1].asset_depreciable_value, 0.0)

    def test_board_entries_protected(self):
        asset = self._create_asset()
        with self.assertRaises(UserError):
            self._board(asset)[0].unlink()

    # -------------------------------------------------------------------------
    # Pause / resume
    # -------------------------------------------------------------------------

    def test_pause_resume(self):
        asset = self._create_asset()
        self._autopost('2025-02-28')

        with freeze_time('2025-03-16'):
            asset.pause(date(2025, 3, 16))
        self.assertEqual(asset.state, 'paused')
        self.assertFalse(self._drafts(asset))
        partial = self._board(asset).filtered(lambda m: m.date == date(2025, 3, 16))
        self.assertEqual(partial.asset_depreciation_amount, 51.61)  # 16 days of the 31 days period
        self.assertEqual(partial.state, 'posted')
        self.assertEqual(asset.value_residual, 948.39)

        with freeze_time('2025-05-16'):
            asset.resume(date(2025, 5, 16))
        self.assertEqual(asset.state, 'open')
        drafts = self._drafts(asset)
        # May 16th to 31st, 8 months, and the rest of the life added by the 2 months on hold
        self.assertEqual(drafts[0].date, date(2025, 5, 31))
        self.assertEqual(drafts[0].asset_depreciation_amount, 51.61)
        self.assertEqual(drafts[1].asset_depreciation_amount, 100.0)
        self.assertEqual(drafts[-1].date, date(2026, 2, 28))
        self.assertAlmostEqual(sum(drafts.mapped('asset_depreciation_amount')), 948.39)
        self.assertEqual(drafts[-1].asset_depreciable_value, 0.0)

    def test_pause_before_lock_date(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        self.env.company.fiscalyear_lock_date = date(2025, 3, 31)
        with freeze_time('2025-04-05'), self.assertRaises(UserError):
            asset.pause(date(2025, 3, 16))

    # -------------------------------------------------------------------------
    # Re-evaluation
    # -------------------------------------------------------------------------

    def _modify(self, asset, **vals):
        wizard = self.env['asset.modify'].with_context(active_id=asset.id).create({
            'note': 'Re-evaluation',
            **vals,
        })
        wizard.modify()
        return wizard

    def test_modify_value_decrease(self):
        asset = self._create_asset()
        self._autopost('2025-02-28')
        with freeze_time('2025-02-28'):
            self._modify(asset, date=date(2025, 2, 28), new_depreciable_value=600.0)

        revaluation = self._board(asset).filtered(lambda m: m.asset_entry_type == 'revaluation')
        self.assertEqual(revaluation.asset_depreciation_amount, 400.0)
        self.assertEqual(revaluation.state, 'posted')
        self.assertEqual(asset.value_residual, 600.0)
        drafts = self._drafts(asset)
        self.assertEqual(drafts.mapped('asset_depreciation_amount'), [60.0] * 10)
        self.assertEqual(drafts[0].date, date(2025, 3, 31))

    def test_modify_value_increase(self):
        asset = self._create_asset()
        self._autopost('2025-02-28')
        with freeze_time('2025-02-28'):
            self._modify(asset, date=date(2025, 2, 28), new_depreciable_value=1300.0,
                         increase_counterpart_account_id=self.counterpart_account.id)

        self.assertEqual(self._drafts(asset).mapped('asset_depreciation_amount'), [100.0] * 10)
        child = asset.children_ids
        self.assertEqual(child.value, 300.0)
        self.assertEqual(child.state, 'open')
        self.assertEqual(child.method_end, date(2025, 12, 31))
        child_board = self._board(child)
        self.assertEqual(child_board.mapped('asset_depreciation_amount'), [30.0] * 10)
        self.assertEqual(child_board[0].date, date(2025, 3, 31))
        self.assertEqual(self._balances(child.increase_move_id),
                         {self.asset_account: 300.0, self.counterpart_account: -300.0})

    def test_modify_duration_keeps_ending_date(self):
        asset = self._create_asset(method_end=date(2030, 1, 1))
        with freeze_time('2025-01-16'):
            wizard = self._modify(asset, date=date(2025, 1, 16), method_number=24)
        # the default value is the value left once January is depreciated up to the 16th
        self.assertEqual(wizard.new_depreciable_value, 1148.39)
        self.assertFalse(asset.children_ids)
        self.assertEqual(asset.method_end, date(2030, 1, 1))
        drafts = self._drafts(asset)
        self.assertEqual(len(drafts), 24)
        self.assertEqual(drafts[0].date, date(2025, 1, 31))
        self.assertEqual(drafts[-1].date, date(2026, 12, 31))
        self.assertAlmostEqual(sum(drafts.mapped('asset_depreciation_amount')), 1148.39)

    # -------------------------------------------------------------------------
    # Sale / disposal
    # -------------------------------------------------------------------------

    def test_sell_with_gain(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        invoice = self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-03-31', post=True)
        revenue_line = invoice.invoice_line_ids

        wizard = self.env['asset.sell'].with_context(active_model='account.asset.asset', active_id=asset.id).create({
            'action': 'sell',
            'date': date(2025, 3, 31),
            'sale_invoice_ids': [Command.set(invoice.ids)],
            'sale_line_ids': [Command.set(revenue_line.ids)],
        })
        with freeze_time('2025-03-31'):
            wizard.action_confirm()

        self.assertEqual(asset.state, 'close')
        self.assertEqual(asset.disposal_date, date(2025, 3, 31))
        self.assertFalse(self._drafts(asset))
        self.assertEqual(asset.disposal_result, 100.0)
        self.assertEqual(asset.disposal_move_id.asset_entry_type, 'sale')
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -1200.0,
            self.accumulated_account: 300.0,
            revenue_line.account_id: 1000.0,
            self.gain_account: -100.0,
        })

    def test_dispose_with_partial_period(self):
        asset = self._create_asset()
        self._autopost('2025-02-28')
        with freeze_time('2025-03-16'):
            asset.set_to_close(disposal_date=date(2025, 3, 16))

        self.assertEqual(asset.state, 'close')
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -1200.0,
            self.accumulated_account: 251.61,
            self.loss_account: 948.39,
        })

    def test_sell_requires_disposed_gross_increases(self):
        asset = self._create_asset()
        self._autopost('2025-02-28')
        with freeze_time('2025-02-28'):
            self._modify(asset, date=date(2025, 2, 28), new_depreciable_value=1300.0,
                         increase_counterpart_account_id=self.counterpart_account.id)
            invoice = self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-02-28', post=True)
            with self.assertRaises(UserError):
                asset.set_to_close(sale_lines=invoice.invoice_line_ids, disposal_date=date(2025, 2, 28))
            asset.set_to_close(disposal_date=date(2025, 2, 28))
        self.assertEqual(asset.children_ids.state, 'close')

    def test_partial_sale(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        invoice = self.init_invoice('out_invoice', amounts=[325.0], invoice_date='2025-03-31', post=True)
        wizard = self.env['asset.sell'].with_context(active_model='account.asset.asset', active_id=asset.id).create({
            'action': 'sell',
            'scope': 'partial',
            'disposed_percent': 25.0,
            'date': date(2025, 3, 31),
            'sale_invoice_ids': [Command.set(invoice.ids)],
        })
        self.assertEqual(wizard.disposed_value, 300.0)
        with freeze_time('2025-03-31'):
            wizard.action_confirm()

        partial = self._board(asset).filtered(lambda m: m.asset_entry_type == 'partial_disposal')
        self.assertEqual(partial.state, 'posted')
        # a quarter of the gross value (300) and of the depreciation (75) leave the books, sold 325
        self.assertEqual(self._balances(partial), {
            self.asset_account: -300.0,
            self.accumulated_account: 75.0,
            invoice.invoice_line_ids.account_id: 325.0,
            self.gain_account: -100.0,
        })
        self.assertEqual(asset.state, 'open')
        self.assertEqual(asset.value, 900.0)
        self.assertEqual(asset.value_residual, 675.0)
        self.assertEqual(partial.asset_cumulative_depreciation, 225.0)
        self.assertEqual(partial.asset_depreciable_value, 675.0)
        drafts = self._drafts(asset)
        self.assertEqual(drafts.mapped('asset_depreciation_amount'), [75.0] * 9)
        self.assertEqual(drafts[-1].asset_cumulative_depreciation, 900.0)
        with self.assertRaises(UserError):
            partial.button_draft()
        with self.assertRaises(UserError), freeze_time('2025-04-05'):
            partial._reverse_moves(cancel=True)

        self._autopost('2025-06-30')
        with freeze_time('2025-06-30'):
            asset.set_to_close(disposal_date=date(2025, 6, 30))
        self.assertEqual(self._balances(asset.disposal_move_id), {
            self.asset_account: -900.0,
            self.accumulated_account: 450.0,
            self.loss_account: 450.0,
        })

        wizard = self.env['asset.depreciation.schedule'].create({
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
            'category_ids': [Command.set(self.category.ids)],
        })
        line = wizard._get_schedule_data()['register'][0]['lines'][0]
        self.assertEqual((line['cost_additions'], line['cost_disposals'], line['cost_closing']), (1200.0, 1200.0, 0.0))
        self.assertEqual((line['depreciation_charge'], line['depreciation_disposals'], line['depreciation_closing']),
                         (525.0, 525.0, 0.0))
        self.assertTrue(line['is_disposed'])

        # before the final disposal, the asset shows partly disposed
        wizard.date_to = date(2025, 4, 30)
        line = wizard._get_schedule_data()['register'][0]['lines'][0]
        self.assertEqual((line['cost_additions'], line['cost_disposals'], line['cost_closing']), (1200.0, 300.0, 900.0))
        self.assertEqual((line['depreciation_charge'], line['depreciation_disposals'], line['depreciation_closing']),
                         (375.0, 75.0, 300.0))
        self.assertTrue(line['is_partly_disposed'])

    def test_partial_disposal_checks(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        with freeze_time('2025-03-31'):
            with self.assertRaises(UserError):
                asset._dispose_partially(date(2025, 3, 31), 1.0)
            with self.assertRaises(UserError):
                asset._dispose_partially(date(2025, 4, 30), 0.5)
            # paused: nothing to depreciate, the resumed board uses the remaining values
            asset.pause(date(2025, 3, 31))
            asset._dispose_partially(date(2025, 3, 31), 0.5)
        self.assertEqual(asset.state, 'paused')
        self.assertEqual(asset.value_residual, 450.0)
        with freeze_time('2025-04-01'):
            asset.resume(date(2025, 4, 1))
        self.assertAlmostEqual(sum(self._drafts(asset).mapped('asset_depreciation_amount')), 450.0)

    # -------------------------------------------------------------------------
    # Assets from vendor bills
    # -------------------------------------------------------------------------

    def _create_bill(self, **line_vals):
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-01',
            'invoice_line_ids': [Command.create({
                'name': 'Laptop',
                'price_unit': 1000.0,
                'account_id': self.asset_account.id,
                'tax_ids': [],
                **line_vals,
            })],
        })

    def test_assets_from_bill_account(self):
        self.category.write({'create_from_bill': True, 'asset_per_unit': True})
        with self.assertRaises(ValidationError):
            self.category.copy()
        billing_user = new_test_user(
            self.env, login='asset_billing', groups='account.group_account_invoice',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        bill = self._create_bill(quantity=3.0, price_unit=333.34).with_user(billing_user)
        with freeze_time('2025-01-15'):
            bill.action_post()

        self.assertEqual(bill.invoice_line_ids.asset_category_id, self.category)
        assets = bill.asset_ids.sorted('id')
        self.assertEqual(assets.mapped('value'), [333.34, 333.34, 333.34])
        self.assertEqual(assets.mapped('name'), ['Laptop (1/3)', 'Laptop (2/3)', 'Laptop (3/3)'])
        self.assertEqual(set(assets.mapped('state')), {'open'})

        # the credit note keeps the category of the line but does not create assets
        with freeze_time('2025-01-20'):
            refund = bill._reverse_moves()
            refund.invoice_date = date(2025, 1, 20)
            refund.action_post()
        self.assertEqual(refund.invoice_line_ids.asset_category_id, self.category)
        self.assertFalse(refund.asset_ids)
        self.assertEqual(len(self.env['account.asset.asset'].search([('category_id', '=', self.category.id)])), 3)

    def test_bill_account_without_category(self):
        bill = self._create_bill()
        with freeze_time('2025-01-15'):
            bill.action_post()
        self.assertFalse(bill.asset_ids)

    # -------------------------------------------------------------------------
    # Reversal and cancellation
    # -------------------------------------------------------------------------

    def test_reverse_depreciation_entry(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        march = self._board(asset).filtered(lambda m: m.date == date(2025, 3, 31))

        with freeze_time('2025-04-05'):
            march._reverse_moves(cancel=True)

        self.assertTrue(march.asset_entry_reversed)
        self.assertEqual(asset.value_residual, 1000.0)
        drafts = self._drafts(asset)
        self.assertEqual(drafts[0].date, date(2025, 4, 30))
        self.assertEqual(drafts[0].asset_depreciation_amount, 200.0)
        self.assertEqual(self._balances(drafts[0]), {self.accumulated_account: -200.0, self.expense_account: 200.0})
        self.assertAlmostEqual(sum(drafts.mapped('asset_depreciation_amount')), 1000.0)

    def test_cancel_asset(self):
        asset = self._create_asset()
        self._autopost('2025-03-31')
        moves = self._board(asset)
        self.env.company.fiscalyear_lock_date = date(2025, 1, 31)

        with freeze_time('2025-04-05'):
            asset.set_to_cancelled()

        self.assertEqual(asset.state, 'cancelled')
        # the locked January entry is reversed, the others are deleted
        self.assertEqual(moves.exists().mapped('date'), [date(2025, 1, 31)])
        self.assertTrue(moves.exists().reversal_move_ids)

    def test_bill_reset_to_draft_cancels_asset(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-01',
            'invoice_line_ids': [Command.create({
                'name': 'Laptop',
                'price_unit': 1200.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [],
            })],
        })
        with freeze_time('2025-01-15'):
            bill.action_post()
        asset = bill.asset_ids
        self.assertEqual(asset.state, 'open')
        self._autopost('2025-01-31')

        with freeze_time('2025-02-05'):
            bill.button_draft()
            self.assertEqual(asset.state, 'cancelled')
            self.assertFalse(asset._get_board_moves().exists())
            bill.action_post()
        new_asset = bill.asset_ids.filtered(lambda a: a.state == 'open')
        self.assertEqual(len(new_asset), 1)
        self.assertNotEqual(new_asset, asset)

    # -------------------------------------------------------------------------
    # Depreciation schedule
    # -------------------------------------------------------------------------

    def test_depreciation_schedule(self):
        running = self._create_asset(name='Running', date=date(2024, 7, 1), validate_on='2025-03-31')
        sold = self._create_asset(name='Sold', validate_on='2025-03-31')
        with freeze_time('2025-03-31'):
            sold.set_to_close(disposal_date=date(2025, 3, 31))
        self._autopost('2025-12-31')

        wizard = self.env['asset.depreciation.schedule'].create({
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
            'category_ids': [Command.set(self.category.ids)],
        })
        schedule = wizard._get_schedule_data()
        lines = {line['asset']: line for line in schedule['register'][0]['lines']}
        movement_keys = (
            'cost_opening', 'cost_additions', 'cost_disposals', 'cost_closing', 'depreciation_opening',
            'depreciation_acquired', 'depreciation_charge', 'depreciation_disposals', 'depreciation_closing',
            'nbv_opening', 'nbv_closing')
        self.assertDictEqual({key: lines[running][key] for key in movement_keys}, {
            'cost_opening': 1200.0, 'cost_additions': 0.0, 'cost_disposals': 0.0, 'cost_closing': 1200.0,
            'depreciation_opening': 600.0, 'depreciation_acquired': 0.0, 'depreciation_charge': 600.0,
            'depreciation_disposals': 0.0, 'depreciation_closing': 1200.0, 'nbv_opening': 600.0, 'nbv_closing': 0.0,
        })
        self.assertEqual(lines[running]['depreciated_percent'], 100)
        self.assertDictEqual({key: lines[sold][key] for key in movement_keys}, {
            'cost_opening': 0.0, 'cost_additions': 1200.0, 'cost_disposals': 1200.0, 'cost_closing': 0.0,
            'depreciation_opening': 0.0, 'depreciation_acquired': 0.0, 'depreciation_charge': 300.0,
            'depreciation_disposals': 300.0, 'depreciation_closing': 0.0, 'nbv_opening': 0.0, 'nbv_closing': 0.0,
        })
        self.assertTrue(lines[sold]['is_disposed'])
        self.assertEqual(lines[sold]['disposed_nbv'], 900.0)
        self.assertEqual(schedule['total']['cost_closing'], 1200.0)
        self.assertEqual(schedule['categories'], [{'name': self.category.name, 'movements': schedule['total']}])

        # the movement statement adds up: opening + movements = closing, for the cost and the depreciation
        total = schedule['total']
        self.assertEqual(total['cost_opening'] + total['cost_additions'] - total['cost_disposals'], total['cost_closing'])
        self.assertEqual(
            total['depreciation_opening'] + total['depreciation_acquired'] + total['depreciation_charge']
            - total['depreciation_disposals'], total['depreciation_closing'])
        rows = wizard._get_statement_rows(schedule['categories'])
        self.assertNotIn('depreciation_acquired', [row[2] for row in rows])
        self.assertEqual(wizard._get_statement_tables(schedule['categories'], total)[-1][-1][1], total)

        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_asset.report_depreciation_schedule', wizard.ids)[0]
        self.assertIn(b'Depreciation Schedule', html)
        self.assertIn(b'Movement by Category', html)
        self.assertIn(b'Asset Register', html)
