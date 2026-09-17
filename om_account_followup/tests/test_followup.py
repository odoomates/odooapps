from datetime import date

from freezegun import freeze_time
from markupsafe import Markup

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools.misc import format_date, formatLang

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
@freeze_time('2026-03-01')
class TestFollowup(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()
        cls.company = cls.env.company
        cls.company.external_report_layout_id = cls.env.ref('web.external_layout_standard')
        cls.customer = cls.env['res.partner'].create({
            'name': 'Late Payer',
            'email': 'late.payer@example.com',
        })
        # levels are created in reverse order so that record ids and delays disagree
        cls.plan = cls.env['followup.followup'].create({'company_id': cls.company.id, 'is_default': True})
        FollowupLine = cls.env['followup.line']
        cls.level_30 = FollowupLine.create({
            'name': 'Second reminder', 'delay': 30, 'followup_id': cls.plan.id,
            'send_email': True, 'send_letter': True,
        })
        cls.level_15 = FollowupLine.create({
            'name': 'First reminder', 'delay': 15, 'followup_id': cls.plan.id,
            'send_email': True, 'send_letter': True,
        })

    def _create_customer_invoice(self, invoice_date, amount=1000.0, company=None):
        return self.init_invoice(
            'out_invoice', partner=self.customer, invoice_date=invoice_date,
            amounts=[amount], company=company, post=True,
        )

    def _receivable_line(self, invoice):
        return invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')

    def _stat_line(self):
        stat = self.env['followup.stat.by.partner']
        return stat.browse(stat._get_stat_id(self.customer.id, self.company.id))

    def _run_wizard(self, run_date):
        wizard = self.env['followup.print'].create({'date': run_date, 'followup_id': self.plan.id})
        return wizard.do_process()

    def test_wizard_processes_levels_on_each_run(self):
        invoice = self._create_customer_invoice('2026-01-01')

        action = self._run_wizard('2026-01-20')
        self.assertEqual(self._receivable_line(invoice).followup_line_id, self.level_15)
        self.assertEqual(self._stat_line().max_followup_id, self.level_15)
        self.assertTrue(action['context']['needprinting'])
        self.assertIn('1 email(s) sent', action['context']['description'])
        self.assertTrue(self.env['mail.mail'].search([
            ('model', '=', 'res.partner'), ('res_id', '=', self.customer.id),
        ]))

        self.env.invalidate_all()
        self._run_wizard('2026-02-15')
        self.assertEqual(self._receivable_line(invoice).followup_line_id, self.level_30)
        self.assertEqual(self._stat_line().max_followup_id, self.level_30)

    def test_max_level_uses_highest_delay(self):
        invoice_1 = self._create_customer_invoice('2026-01-01')
        invoice_2 = self._create_customer_invoice('2026-01-10')
        self._receivable_line(invoice_1).followup_line_id = self.level_30
        self._receivable_line(invoice_2).followup_line_id = self.level_15
        self.assertLess(self.level_30.id, self.level_15.id)
        self.assertEqual(self._stat_line().max_followup_id, self.level_30)

    def test_followup_table_html_in_other_language(self):
        self.env['res.lang']._activate_lang('fr_FR')
        self._create_customer_invoice('2026-01-25', amount=1234.5)
        customer = self.customer.with_context(lang='fr_FR')

        html = customer.get_followup_table_html()
        self.assertIsInstance(html, Markup)
        self.assertIn(format_date(customer.env, date(2026, 1, 25)), html)
        self.assertIn('<b>%s</b>' % formatLang(customer.env, 1234.5, digits=2), html)

        template = self.env.ref('om_account_followup.email_template_om_account_followup_default')
        body = template._render_field('body_html', customer.ids)[customer.id]
        self.assertIn('<table', body)
        self.assertNotIn('&lt;table', body)

    def test_statement_report(self):
        self._create_customer_invoice('2026-01-01', amount=1234.5)
        self.level_15.description = "Dear %(partner_name)s,\nPlease pay."
        self._receivable_line(self.customer.invoice_ids).followup_line_id = self.level_15

        action = self.customer.action_followup_print_statement()
        self.assertEqual(action['report_name'], 'om_account_followup.report_customer_statement')
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_followup.report_customer_statement', self.customer.ids)[0].decode()
        self.assertIn('Dear Late Payer,\nPlease pay.', html)
        self.assertNotIn('&lt;br', html)
        # amounts go through the monetary widget: grouped with the currency decimals
        self.assertIn('1,234.50', html)
        self.assertNotIn('1234.5<', html)
        self.assertIn('Over 90 Days', html)
        self.assertEqual(self.customer.message_ids.mapped('body').count(
            Markup('<p>Customer statement printed</p>')), 1)

    def test_search_methods_match_computed_values(self):
        self._create_customer_invoice('2026-01-01', amount=500.0)
        self._create_customer_invoice('2026-12-31', amount=700.0)
        partners = self.customer + self.partner_a + self.partner_b
        checks = {
            'payment_amount_due': [('=', 0), ('!=', 0), ('>', 1000), ('<=', 1200), ('=', False)],
            'payment_amount_overdue': [('=', 500), ('!=', 500), ('>', 0), ('=', False)],
            'payment_earliest_due_date': [
                ('=', date(2026, 1, 1)), ('!=', date(2026, 1, 1)), ('<', date(2026, 6, 1)),
                ('=', False), ('!=', False),
            ],
        }
        compare = {
            '=': lambda a, b: a == b, '!=': lambda a, b: a != b, '>': lambda a, b: bool(a) and a > b,
            '<': lambda a, b: bool(a) and a < b, '<=': lambda a, b: a <= b,
        }
        for field_name, conditions in checks.items():
            for operator, value in conditions:
                with self.subTest(field=field_name, operator=operator, value=value):
                    found = self.env['res.partner'].search([
                        ('id', 'in', partners.ids), (field_name, operator, value),
                    ])
                    expected = partners.filtered(lambda p: compare[operator](
                        p[field_name],
                        value if value is not False or field_name == 'payment_earliest_due_date' else 0.0,
                    ))
                    self.assertEqual(found, expected)

    def test_amounts_follow_active_company(self):
        self._create_customer_invoice('2026-01-01', amount=100.0)
        self._create_customer_invoice('2026-01-01', amount=300.0, company=self.company_data_2['company'])

        self.assertEqual(self.customer.payment_amount_due, 100.0)
        customer_2 = self.customer.with_company(self.company_data_2['company'])
        self.assertEqual(customer_2.payment_amount_due, 300.0)
        self.assertEqual(
            self.env['res.partner'].with_company(self.company_data_2['company']).search([
                ('id', '=', self.customer.id), ('payment_amount_due', '=', 300.0),
            ]),
            self.customer,
        )

    def test_responsible_notification(self):
        user = self.env.user
        self.customer.payment_responsible_id = user
        message = self.customer.message_ids.filtered(lambda m: 'You became responsible' in (m.body or ''))
        self.assertEqual(message.message_type, 'comment')
        self.assertIn(user.partner_id, message.partner_ids)
        self.assertIn('data-oe-model="res.partner"', message.body)

    def test_description_placeholders_are_validated(self):
        for description in ('Dear %(unknown)s', 'Pay 50% now'):
            with self.subTest(description=description), self.assertRaises(ValidationError):
                self.level_15.description = description
        self.level_15.description = 'Dear %(partner_name)s, pay 50%% now'

    def test_manual_action_level(self):
        responsible = new_test_user(
            self.env, login='collector', name='Collector <b>', groups='account.group_account_user')
        level_40 = self.env['followup.line'].create({
            'name': 'Call the customer', 'delay': 40, 'followup_id': self.plan.id,
            'send_email': False, 'send_letter': False, 'manual_action': True,
            'manual_action_note': 'Call them', 'manual_action_responsible_id': responsible.id,
        })
        invoice = self._create_customer_invoice('2026-01-01')
        self._receivable_line(invoice).followup_line_id = self.level_30

        action = self._run_wizard('2026-02-15')
        self.assertEqual(self.customer.latest_followup_level_id, level_40)
        activity = self.customer.activity_ids
        self.assertEqual(activity.activity_type_id, self.env.ref('om_account_followup.mail_activity_type_followup'))
        self.assertEqual(activity.user_id, responsible)
        self.assertIn('Call them', activity.note)
        description = action['context']['description']
        self.assertIn('1 manual action(s) assigned', description)

        # once everything is paid, the next run marks the action as done
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({})._create_payments()
        self._run_wizard('2026-02-20')
        self.assertFalse(self.customer.activity_ids)

    def test_stat_ids_do_not_collide(self):
        stat = self.env['followup.stat.by.partner']
        self.assertNotEqual(stat._get_stat_id(1, 10000), stat._get_stat_id(2, 0))
        self._create_customer_invoice('2026-01-01')
        line = self._stat_line()
        self.assertEqual((line.partner_id, line.company_id), (self.customer, self.company))

    def test_wizard_requires_accountant(self):
        billing_user = new_test_user(
            self.env, login='billing', groups='account.group_account_invoice',
            company_id=self.company.id,
        )
        with self.assertRaises(AccessError):
            self.env['followup.print'].with_user(billing_user).create({'followup_id': self.plan.id})
        stat = self.env['followup.stat'].with_user(billing_user)
        self.assertTrue(stat.has_access('read'))
        self.assertFalse(stat.has_access('write'))

        manager = new_test_user(
            self.env, login='accounting_admin', groups='account.group_account_manager',
            company_id=self.company.id,
        )
        self._create_customer_invoice('2026-01-01')
        wizard = self.env['followup.print'].with_user(manager).create(
            {'date': '2026-01-20', 'followup_id': self.plan.id})
        self.assertIn('1 email(s) sent', wizard.do_process()['context']['description'])

    def test_default_template_is_optional(self):
        FollowupLine = self.env['followup.line']
        template = self.env.ref('om_account_followup.email_template_om_account_followup_default')
        self.assertEqual(FollowupLine.default_get(['email_template_id'])['email_template_id'], template.id)
        template.unlink()
        self.assertFalse(FollowupLine.default_get(['email_template_id']).get('email_template_id'))

    def test_email_subject_uses_followup_company(self):
        company_2 = self.company_data_2['company']
        self.assertNotEqual(self.env.user.company_id, company_2)
        # a new company gets a plan of its own
        plan_2 = self.env['followup.followup']._get_default_plan(company_2)
        self.assertTrue(plan_2.is_default)
        self.assertEqual(plan_2._get_levels().mapped('delay'), [7, 21, 45])
        self._create_customer_invoice('2026-01-01', company=company_2)

        self.env['followup.print'].with_company(company_2).create({
            'date': '2026-01-20', 'followup_id': plan_2.id,
        }).do_process()
        mail = self.env['mail.mail'].search([('model', '=', 'res.partner'), ('res_id', '=', self.customer.id)])
        self.assertEqual(mail.subject, '%s Payment Reminder' % company_2.name)

    def test_translations_are_loaded(self):
        self.env['res.lang']._activate_lang('fr_FR')
        self.env['ir.module.module']._load_module_terms(['om_account_followup'], ['fr_FR'])
        self._create_customer_invoice('2026-01-01')

        wizard = self.env['followup.print'].with_context(lang='fr_FR').create({
            'date': '2026-01-20', 'followup_id': self.plan.id,
        })
        self.assertIn('1 e-mail(s) envoyé(s)', wizard.do_process()['context']['description'])
        subject = self.env.ref(
            'om_account_followup.email_template_om_account_followup_default').with_context(lang='fr_FR').subject
        self.assertEqual(subject, '{{ env.company.name }}  Rappel de paiement')

    def test_daily_automatic_sending(self):
        self._create_customer_invoice('2026-01-01')
        sender = new_test_user(self.env, login='followup_sender', groups='account.group_account_user',
                               email='sender@example.com', company_id=self.company.id,
                               company_ids=[Command.set(self.company.ids)])
        cron_model = self.env['followup.followup']

        with freeze_time('2026-01-25'):
            cron_model._cron_send_followups()
        self.assertFalse(self._receivable_line(self.customer.invoice_ids).followup_line_id)

        self.plan.write({'auto_send': True, 'auto_user_id': sender.id})
        with freeze_time('2026-01-25'):
            cron_model._cron_send_followups()
        self.assertEqual(self._receivable_line(self.customer.invoice_ids).followup_line_id, self.level_15)
        mail = self.env['mail.mail'].search([('model', '=', 'res.partner'), ('res_id', '=', self.customer.id)])
        self.assertTrue(mail)
        self.assertIn('sender@example.com', mail.email_from)
        # automatic runs do not announce letters nobody prints
        self.assertFalse(self.customer.message_ids.filtered(lambda message: 'will be sent' in (message.body or '')))
        self.assertEqual(self.plan.last_auto_send, date(2026, 1, 25))

        # already sent today: nothing happens again
        self._receivable_line(self.customer.invoice_ids).followup_line_id = False
        with freeze_time('2026-01-25'):
            cron_model._cron_send_followups()
        self.assertFalse(self._receivable_line(self.customer.invoice_ids).followup_line_id)
        # the next day, the reminders due are sent
        with freeze_time('2026-02-01'):
            cron_model._cron_send_followups()
        self.assertEqual(self._receivable_line(self.customer.invoice_ids).followup_line_id, self.level_30)
