from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanAutomation(LoanCommon):

    def _reclassifications(self, loan):
        return loan.move_ids.filtered(lambda move: move.loan_entry_type == 'reclassification')

    @freeze_time('2025-04-03')
    def test_monthly_reclassification(self):
        """ The companies that ask for it have their running loans reclassified at the end of the month
        before, once. """
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        self.env['account.loan']._cron_reclassify()
        self.assertFalse(self._reclassifications(loan), "the company did not ask for it")
        self.env.company.loan_auto_reclassify = True
        self.env['account.loan']._cron_reclassify()
        entry = self._reclassifications(loan)
        self.assertEqual(entry.date, date(2025, 3, 31))
        self.assertEqual(loan._account_balance_at(self.short_term_account, date(2025, 3, 31)),
                         loan._principal_due_within(date(2025, 3, 31)))
        self.env['account.loan']._cron_reclassify()
        self.assertEqual(self._reclassifications(loan), entry, "once a month end")

    @freeze_time('2025-04-03')
    def test_monthly_reclassification_failure(self):
        """ A loan that cannot be reclassified says why, once, and is reclassified when it can. """
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        self.env.company.loan_auto_reclassify = True
        self.env.company.fiscalyear_lock_date = date(2025, 3, 31)
        messages = len(loan.message_ids)
        self.env['account.loan']._cron_reclassify()
        self.env['account.loan']._cron_reclassify()
        self.assertFalse(self._reclassifications(loan))
        self.assertEqual(len(loan.message_ids), messages + 1)
        self.env.company.fiscalyear_lock_date = False
        self.env['account.loan']._cron_reclassify()
        self.assertEqual(self._reclassifications(loan).date, date(2025, 3, 31))
