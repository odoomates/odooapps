from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDeferred(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.expense_account = cls._account('expense')
        cls.income_account = cls._account('income')
        cls.prepaid_account = cls.env['account.account'].create({
            'name': 'Prepaid Expenses', 'code': 'OMDEF1',
            'account_type': 'asset_current',
        })
        cls.deferred_income_account = cls.env['account.account'].create({
            'name': 'Deferred Income', 'code': 'OMDEF2',
            'account_type': 'liability_current',
        })
        journal = cls.env['account.journal'].search([('type', '=', 'general')], limit=1)
        company.write({
            'om_deferred_expense_journal_id': journal.id,
            'om_deferred_revenue_journal_id': journal.id,
            'om_deferred_expense_account_id': cls.prepaid_account.id,
            'om_deferred_revenue_account_id': cls.deferred_income_account.id,
            'om_deferred_expense_method': 'month',
            'om_deferred_revenue_method': 'month',
            # Generated on demand, so each test says when.
            'om_deferred_expense_generation': 'manual',
            'om_deferred_revenue_generation': 'manual',
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Deferred Partner'})

    @classmethod
    def _account(cls, account_type):
        return cls.env['account.account'].search(
            [('account_type', '=', account_type)], limit=1)

    def _bill(self, amount=1200.0, start='2026-01-01', end='2026-12-31', date='2026-01-01'):
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': date,
            'date': date,
            'invoice_line_ids': [(0, 0, {
                'name': 'Yearly insurance',
                'quantity': 1,
                'price_unit': amount,
                'account_id': self.expense_account.id,
                'tax_ids': [(6, 0, [])],
                'om_deferred_start_date': start,
                'om_deferred_end_date': end,
            })],
        })
        move.action_post()
        return move

    def _deferred_line(self, move):
        return move.line_ids.filtered(lambda line: line._om_is_deferrable())

    # -- the schedule --------------------------------------------------------

    def test_a_year_splits_into_twelve_equal_periods(self):
        line = self._deferred_line(self._bill())
        schedule = line._om_deferral_schedule()
        self.assertEqual(len(schedule), 12)
        self.assertEqual([amount for _date, amount in schedule], [100.0] * 12)
        # Recognised at each month end.
        self.assertEqual(str(schedule[0][0]), '2026-01-31')
        self.assertEqual(str(schedule[-1][0]), '2026-12-31')

    def test_the_schedule_always_adds_back_up_to_the_line(self):
        # 1000 over 3 months does not divide evenly; the remainder has to land
        # somewhere rather than being left on the deferral account forever.
        line = self._deferred_line(
            self._bill(amount=1000.0, start='2026-01-01', end='2026-03-31'))
        schedule = line._om_deferral_schedule()
        self.assertEqual(len(schedule), 3)
        self.assertAlmostEqual(sum(amount for _d, amount in schedule), 1000.0, places=2)

    def test_a_part_month_is_weighted_by_its_days(self):
        line = self._deferred_line(
            self._bill(amount=310.0, start='2026-01-17', end='2026-02-28'))
        schedule = line._om_deferral_schedule()
        self.assertEqual(len(schedule), 2)
        # 15 of January's 31 days, then the whole of February.
        january, february = (amount for _d, amount in schedule)
        self.assertLess(january, february)
        self.assertAlmostEqual(january + february, 310.0, places=2)

    def test_full_months_counts_the_whole_months_only(self):
        self.env.company.om_deferred_expense_method = 'full_month'
        line = self._deferred_line(
            self._bill(amount=300.0, start='2026-01-17', end='2026-03-02'))
        schedule = line._om_deferral_schedule()
        # two whole months between the dates: the days of March get nothing
        self.assertEqual([amount for _d, amount in schedule], [150.0, 150.0])

    def test_days_weighs_by_the_calendar(self):
        self.env.company.om_deferred_expense_method = 'day'
        line = self._deferred_line(
            self._bill(amount=590.0, start='2026-01-01', end='2026-02-28'))
        schedule = line._om_deferral_schedule()
        january, february = (amount for _d, amount in schedule)
        # 31 days against 28, out of 59.
        self.assertAlmostEqual(january, 310.0, places=2)
        self.assertAlmostEqual(february, 280.0, places=2)

    # -- the entries ---------------------------------------------------------

    def test_a_bill_parks_the_cost_then_releases_it_monthly(self):
        bill = self._bill()
        bill.action_om_generate_deferrals()
        deferrals = bill.om_deferral_ids
        # One entry taking the cost out, then one per month putting it back.
        self.assertEqual(len(deferrals), 13)

        parked = deferrals.filtered(lambda move: move.date == bill.date)
        expense_line = parked.line_ids.filtered(
            lambda line: line.account_id == self.expense_account)
        prepaid_line = parked.line_ids.filtered(
            lambda line: line.account_id == self.prepaid_account)
        # The cost leaves profit and loss and sits on the balance sheet.
        self.assertAlmostEqual(expense_line.balance, -1200.0, places=2)
        self.assertAlmostEqual(prepaid_line.balance, 1200.0, places=2)

        releases = deferrals - parked
        self.assertAlmostEqual(
            sum(releases.line_ids.filtered(
                lambda line: line.account_id == self.expense_account).mapped('balance')),
            1200.0, places=2)
        # Nothing is left behind on the deferral account.
        self.assertAlmostEqual(
            sum(deferrals.line_ids.filtered(
                lambda line: line.account_id == self.prepaid_account).mapped('balance')),
            0.0, places=2)

    def test_an_invoice_defers_revenue_the_other_way_round(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': '2026-01-01',
            'date': '2026-01-01',
            'invoice_line_ids': [(0, 0, {
                'name': 'Yearly subscription',
                'quantity': 1,
                'price_unit': 1200.0,
                'account_id': self.income_account.id,
                'tax_ids': [(6, 0, [])],
                'om_deferred_start_date': '2026-01-01',
                'om_deferred_end_date': '2026-12-31',
            })],
        })
        invoice.action_post()
        invoice.action_om_generate_deferrals()

        parked = invoice.om_deferral_ids.filtered(lambda m: m.date == invoice.date)
        income_line = parked.line_ids.filtered(
            lambda line: line.account_id == self.income_account)
        deferred_line = parked.line_ids.filtered(
            lambda line: line.account_id == self.deferred_income_account)
        # Income is taken back out (debited) and parked as a liability.
        self.assertGreater(income_line.balance, 0)
        self.assertLess(deferred_line.balance, 0)

    def test_deferrals_post_themselves_when_their_date_arrives(self):
        bill = self._bill()
        bill.action_om_generate_deferrals()
        today = fields.Date.context_today(bill)
        # the entries whose date has come are in the books at once, the others post themselves later
        for move in bill.om_deferral_ids:
            if move.date <= today:
                self.assertEqual(move.state, 'posted')
            else:
                self.assertEqual((move.state, move.auto_post), ('draft', 'at_date'))

    def test_generating_on_posting_when_the_company_asks_for_it(self):
        self.env.company.om_deferred_expense_generation = 'on_post'
        bill = self._bill()
        self.assertEqual(len(bill.om_deferral_ids), 13)

    def test_a_line_inside_a_single_period_is_left_alone(self):
        bill = self._bill(start='2026-01-05', end='2026-01-20')
        with self.assertRaises(UserError):
            bill.action_om_generate_deferrals()
        self.assertFalse(bill.om_deferral_ids)

    def test_resetting_the_document_takes_its_deferrals_with_it(self):
        bill = self._bill()
        bill.action_om_generate_deferrals()
        self.assertTrue(bill.om_deferral_ids)
        bill.button_draft()
        # the posted ones stay, each answered by its reversal; the ones still to come are gone
        self.assertFalse(bill.om_deferral_ids.filtered(lambda move: move.state == 'draft'))
        posted = bill.om_deferral_ids
        reversals = self.env['account.move'].search([('reversed_entry_id', 'in', posted.ids)])
        self.assertEqual(len(reversals), len(posted))

    def test_resetting_reverses_deferrals_that_are_already_posted(self):
        """Posted deferrals are cancelled out; the ones still to come are dropped.

        Deleting a posted entry would rewrite a period that may already be
        closed, so its history stays and a reversal answers it. Odoo will not
        let a future-dated auto-post entry be posted early: only the periods
        that have come round are in the books.
        """
        bill = self._bill()
        bill.action_om_generate_deferrals()
        deferrals = bill.om_deferral_ids
        today = fields.Date.context_today(bill)
        due = deferrals.filtered(lambda move: move.date <= today)
        pending = deferrals - due
        self.assertTrue(due and pending, 'expected a mix of past and future periods')
        self.assertTrue(all(move.state == 'posted' for move in due))

        bill.button_draft()
        self.assertTrue(all(move.state == 'posted' for move in due),
                        'posted deferrals must survive the reset')
        self.assertFalse(pending.exists(), 'unposted deferrals should be dropped')

        reversals = self.env['account.move'].search([('reversed_entry_id', 'in', due.ids)])
        self.assertEqual(len(reversals), len(due))
        # Everything the deferral put on the balance sheet is taken back off.
        entries = due | reversals
        self.assertAlmostEqual(
            sum(entries.line_ids.filtered(
                lambda line: line.account_id == self.prepaid_account).mapped('balance')),
            0.0, places=2)

    def test_deferrals_are_not_generated_twice(self):
        bill = self._bill()
        bill.action_om_generate_deferrals()
        with self.assertRaises(UserError):
            bill.action_om_generate_deferrals()

    # -- guards --------------------------------------------------------------

    def test_a_backwards_range_is_refused(self):
        with self.assertRaises(ValidationError):
            self._bill(start='2026-12-31', end='2026-01-01')

    def test_one_date_without_the_other_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': self.partner.id,
                'invoice_date': '2026-01-01',
                'invoice_line_ids': [(0, 0, {
                    'name': 'Half a deferral',
                    'quantity': 1,
                    'price_unit': 100.0,
                    'account_id': self.expense_account.id,
                    'tax_ids': [(6, 0, [])],
                    'om_deferred_start_date': '2026-01-01',
                })],
            })

    def test_a_missing_deferral_account_says_so(self):
        self.env.company.om_deferred_expense_account_id = False
        bill = self._bill()
        with self.assertRaises(UserError):
            bill.action_om_generate_deferrals()

    def test_a_balance_sheet_line_is_not_deferrable(self):
        bill = self._bill()
        payable = bill.line_ids.filtered(
            lambda line: line.account_id.internal_group not in ('income', 'expense'))
        self.assertTrue(payable)
        self.assertFalse(any(line._om_is_deferrable() for line in payable))
