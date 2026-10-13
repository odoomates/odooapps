from unittest.mock import patch

from freezegun import freeze_time

from odoo.modules.registry import Registry
from odoo.tools.safe_eval import safe_eval

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAutoPostEntries(AccountTestInvoicingCommon):

    def _auto_post_moves(self, domain=()):
        action = self.env['ir.actions.act_window']._for_xml_id('om_recurring_payments.action_move_auto_post')
        return self.env['account.move'].search(safe_eval(action['domain']) + list(domain))

    def _autopost(self):
        # the scheduled action of Odoo 15 commits after each batch, unless in test mode
        with patch.object(Registry, 'in_test_mode', lambda registry: True):
            self.env['account.move']._autopost_draft_entries()

    @freeze_time('2026-01-10')
    def test_auto_post_entries_are_listed_and_stopped(self):
        manual = self.init_invoice('out_invoice', invoice_date='2026-01-15', amounts=[100.0])
        later = self.init_invoice('out_invoice', invoice_date='2026-01-15', amounts=[100.0])
        later.auto_post = True
        bill = self.init_invoice('in_invoice', invoice_date='2026-01-20', amounts=[50.0])
        bill.auto_post = True
        self.assertEqual(self._auto_post_moves(), later | bill)

        # the scheduled action posts the entries on their date: they stay listed
        with freeze_time('2026-01-16'):
            self._autopost()
        self.assertEqual(later.state, 'posted')
        self.assertEqual(bill.state, 'draft')
        self.assertIn(later, self._auto_post_moves([('state', '=', 'posted')]))
        self.assertNotIn(manual, self._auto_post_moves())

        (later | bill).action_stop_auto_post()
        self.assertTrue(later.auto_post, "a posted entry is left as it is")
        self.assertFalse(bill.auto_post)
        self.assertIn('Auto-post stopped', bill.message_ids[0].body)
        with freeze_time('2026-01-21'):
            self._autopost()
        self.assertEqual(bill.state, 'draft')
