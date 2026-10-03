from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


def _has_access(records, operation):
    """ has_access() of Odoo 17 and later: the access rights and the record rules """
    if not records.check_access_rights(operation, raise_exception=False):
        return False
    try:
        records.check_access_rule(operation)
    except AccessError:
        return False
    return True


@tagged('post_install', '-at_install')
@freeze_time('2026-06-30')
class TestFollowupFixes(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.followup = cls.env['followup.followup'].search([('company_id', '=', cls.env.company.id)]) or \
            cls.env['followup.followup'].create({'company_id': cls.env.company.id})
        cls.first_level, cls.second_level = cls.env['followup.line'].create([
            {'name': 'First reminder', 'delay': 15, 'followup_id': cls.followup.id},
            {'name': 'Second reminder', 'delay': 30, 'followup_id': cls.followup.id},
        ])

    def _invoice(self, amount, date='2026-05-01', post=True, partner=None, payment_term=None):
        invoice = self.init_invoice('out_invoice', partner=partner or self.partner_a, amounts=[amount], taxes=[],
                                    invoice_date=date)
        invoice.invoice_payment_term_id = payment_term or self.env.ref('account.account_payment_term_immediate')
        if post:
            invoice.action_post()
        return invoice

    def _receivable(self, invoice):
        return invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')

    def test_draft_invoices_are_not_followed_up(self):
        self._invoice(100.0)
        self._invoice(1000.0, post=False)
        self.env.flush_all()

        self.assertEqual(self.partner_a.payment_amount_due, 100.0)
        self.assertEqual(self.partner_a.payment_amount_overdue, 100.0)
        self.assertEqual(self.partner_a.unreconciled_aml_ids.move_id.mapped('state'), ['posted'])

        stat = self.env['followup.stat.by.partner'].search([('partner_id', '=', self.partner_a.id)])
        self.assertEqual(stat.balance, 100.0)
        self.assertEqual(self.env['followup.stat'].search([('partner_id', '=', self.partner_a.id)]).balance, 100.0)

        wizard = self.env['followup.print'].create({'followup_id': self.followup.id})
        to_update = wizard._get_partners_followp()['to_update']
        self.assertEqual(set(to_update), {str(line.id) for line in self.partner_a.unreconciled_aml_ids})

    def test_the_level_reached_is_the_one_with_the_longest_delay(self):
        # the second level created first: its id is lower than the one of the first level
        plan = self.followup
        plan.followup_line.unlink()
        late, early = self.env['followup.line'].create([
            {'name': 'Late', 'delay': 60, 'followup_id': plan.id},
            {'name': 'Early', 'delay': 10, 'followup_id': plan.id},
        ])
        self._receivable(self._invoice(100.0)).followup_line_id = late
        self._receivable(self._invoice(50.0)).followup_line_id = early
        self.env.flush_all()

        stat = self.env['followup.stat.by.partner'].search([('partner_id', '=', self.partner_a.id)])
        self.assertEqual(stat.max_followup_id, late)
        self.assertEqual(stat.id, stat._get_stat_id(self.partner_a.id, self.env.company.id))

    def test_search_on_the_amounts(self):
        self._invoice(100.0)
        self._invoice(40.0, date='2026-06-29', partner=self.partner_b,
                      payment_term=self.env.ref('account.account_payment_term_30days'))
        partners = self.partner_a | self.partner_b
        Partner = self.env['res.partner']

        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_amount_due', '>', 50)]),
                         self.partner_a)
        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_amount_due', '=', 40)]),
                         self.partner_b)
        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_amount_due', '!=', 40)]),
                         self.partner_a)
        # the invoice of partner_b is due in 30 days
        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_amount_overdue', '>', 0)]),
                         self.partner_a)
        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_earliest_due_date', '<', '2026-06-30')]),
                         self.partner_a)
        self.assertEqual(Partner.search([('id', 'in', partners.ids), ('payment_earliest_due_date', '=', False)]),
                         Partner)

    def test_print_logs_once(self):
        self._invoice(100.0)
        messages = self.partner_a.message_ids
        self.partner_a.do_button_print()
        self.assertEqual(len(self.partner_a.message_ids - messages), 1)

    def test_statistics_are_read_only(self):
        self._invoice(100.0)
        self.env.flush_all()
        manager = new_test_user(self.env, login='followup_manager', groups='account.group_account_manager')
        stat = self.env['followup.stat.by.partner'].with_user(manager).search([('partner_id', '=', self.partner_a.id)])
        self.assertTrue(stat)
        with self.assertRaises(AccessError):
            stat.write({'balance': 0.0})

        employee = new_test_user(self.env, login='followup_employee', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['followup.print'].with_user(employee).create({'followup_id': self.followup.id})

    def test_an_accountant_who_cannot_edit_contacts_sends_reminders(self):
        """ Posting on a contact in 19.0 asks for the right to edit it: the reminders only ask to read it. """
        self._invoice(100.0)
        self.partner_a.email = 'partner_a@example.com'
        accountant = new_test_user(self.env, login='followup_accountant', groups='account.group_account_user',
                                   company_id=self.env.company.id)
        partner = self.partner_a.with_user(accountant)
        self.assertFalse(_has_access(partner, 'write'))

        self.assertTrue(partner._followup_send_email())
        message = self.partner_a.message_ids[:1]
        self.assertEqual(message.author_id, accountant.partner_id)
        activity = partner._followup_schedule_action(self.second_level)
        self.assertEqual(activity.res_id, self.partner_a.id)

    def test_the_old_folder_is_kept_but_not_shown(self):
        menu = self.env.ref('om_account_followup.om_account_followup_main_menu')
        self.assertFalse(menu.child_id)
        self.assertNotIn(menu.id, self.env['ir.ui.menu']._visible_menu_ids())
