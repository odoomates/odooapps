from freezegun import freeze_time

from odoo.tools.safe_eval import safe_eval

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAutoPostEntries(AccountTestInvoicingCommon):

    def _auto_post_moves(self, domain=()):
        action = self.env['ir.actions.act_window']._for_xml_id('om_recurring_payments.action_move_auto_post')
        return self.env['account.move'].search(safe_eval(action['domain']) + list(domain))

    def test_auto_post_entries_are_listed_and_stopped(self):
        manual = self.init_invoice('out_invoice', invoice_date='2026-01-15', amounts=[100.0])
        monthly = self.init_invoice('out_invoice', invoice_date='2026-01-15', amounts=[100.0])
        monthly.auto_post = 'monthly'
        once = self.init_invoice('in_invoice', invoice_date='2026-01-20', amounts=[50.0])
        once.auto_post = 'at_date'
        self.assertEqual(self._auto_post_moves(), monthly | once)

        # posting a recurring entry creates the next one: both stay listed
        with freeze_time('2026-01-16'):
            monthly.action_post()
        self.assertEqual(monthly.state, 'posted')
        next_move = self._auto_post_moves([('auto_post_origin_id', '=', monthly.id), ('state', '=', 'draft')])
        self.assertEqual(len(next_move), 1)
        self.assertEqual(str(next_move.date), '2026-02-15')
        self.assertIn(monthly, self._auto_post_moves())
        self.assertNotIn(manual, self._auto_post_moves())

        (monthly | next_move | once).action_stop_auto_post()
        self.assertEqual(next_move.auto_post, 'no')
        self.assertEqual(once.auto_post, 'no')
        self.assertEqual(monthly.state, 'posted')
        self.assertIn('Auto-post stopped', next_move.message_ids[0].body)
        # the stopped recurrence creates nothing more
        next_move.action_post()
        self.assertFalse(self.env['account.move'].search_count([
            ('auto_post_origin_id', '=', monthly.id), ('state', '=', 'draft')]))
