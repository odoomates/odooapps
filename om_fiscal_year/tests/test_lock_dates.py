from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestLockDates(AccountTestInvoicingCommon):
    """ The Lock Dates wizard: a date set or moved forward is written on the company; a soft lock date removed or
    moved back opens the period through an exception, with its reason. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'fiscalyear_lock_date': False, 'sale_lock_date': False, 'purchase_lock_date': False,
                           'tax_lock_date': False})

    def _save(self, **values):
        wizard = self.env['change.lock.date'].create(values)
        wizard.update_lock_date()
        return wizard

    def _exceptions(self):
        return self.env['account.lock_exception'].search([('company_id', '=', self.company.id)])

    def test_set_and_move_forward(self):
        self._save(fiscalyear_lock_date='2026-03-31')
        self.assertEqual(str(self.company.fiscalyear_lock_date), '2026-03-31')
        self._save(fiscalyear_lock_date='2026-06-30')
        self.assertEqual(str(self.company.fiscalyear_lock_date), '2026-06-30')
        self.assertFalse(self._exceptions(), 'moving a lock date forward needs no exception')

    def test_only_the_changed_dates_are_written(self):
        self.company.sale_lock_date = '2026-01-31'
        written = []
        original = type(self.company).write

        def spy(records, vals):
            written.append(set(vals))
            return original(records, vals)

        with patch.object(type(self.company), 'write', spy):
            self._save(purchase_lock_date='2026-02-28')
        self.assertIn({'purchase_lock_date'}, written)
        self.assertFalse([vals for vals in written if 'hard_lock_date' in vals or 'sale_lock_date' in vals])

    def test_clear_opens_an_exception_for_me(self):
        self.company.fiscalyear_lock_date = '2026-03-31'
        wizard = self.env['change.lock.date'].create({'fiscalyear_lock_date': False})
        self.assertTrue(wizard.exception_needed)
        self.assertEqual(wizard.exception_fields, 'Lock Date for All Users')
        with self.assertRaises(UserError):
            wizard.update_lock_date()

        before = fields.Datetime.now()
        wizard.write({'exception_reason': 'Late vendor bill', 'exception_duration': '1h'})
        wizard.update_lock_date()
        self.assertEqual(str(self.company.fiscalyear_lock_date), '2026-03-31', 'the company keeps its lock date')
        exception = self._exceptions()
        self.assertEqual(exception.lock_date_field, 'fiscalyear_lock_date')
        self.assertFalse(exception.lock_date)
        self.assertEqual(exception.user_id, self.env.user)
        self.assertEqual(exception.reason, 'Late vendor bill')
        self.assertTrue(before + timedelta(minutes=59) <= exception.end_datetime <= before + timedelta(minutes=61))
        # the chatter of the company logs the exception, with its reason, once the tracking is written
        self.env.cr.precommit.run()
        self.assertTrue(self.company.message_ids.filtered(lambda message: 'Late vendor bill' in message.body))

        # the period is open for the user: an entry of February posts
        invoice = self.init_invoice('out_invoice', amounts=[100.0], taxes=[], invoice_date='2026-02-10')
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

    def test_move_back_for_everyone_forever(self):
        self.company.sale_lock_date = '2026-06-30'
        self._save(sale_lock_date='2026-03-31', exception_applies_to='everyone', exception_duration='forever',
                   exception_reason='Reopen Q2 sales')
        exception = self._exceptions()
        self.assertEqual((exception.lock_date_field, str(exception.lock_date)), ('sale_lock_date', '2026-03-31'))
        self.assertFalse(exception.user_id, 'everyone')
        self.assertFalse(exception.end_datetime, 'forever')
        self.assertEqual(str(self.company.sale_lock_date), '2026-06-30')

    def test_one_exception_and_one_change_together(self):
        self.company.write({'fiscalyear_lock_date': '2026-03-31', 'tax_lock_date': '2026-03-31'})
        self._save(fiscalyear_lock_date='2026-06-30', tax_lock_date='2026-02-28', exception_reason='Tax fix')
        self.assertEqual(str(self.company.fiscalyear_lock_date), '2026-06-30', 'moved forward: written')
        self.assertEqual(str(self.company.tax_lock_date), '2026-03-31', 'moved back: kept, through an exception')
        self.assertEqual(self._exceptions().lock_date_field, 'tax_lock_date')
