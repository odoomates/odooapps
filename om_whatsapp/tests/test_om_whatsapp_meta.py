import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.om_whatsapp.tools import MetaApi, MetaApiError

from .fake_meta import APP_ID, APP_SECRET, PERMANENT_TOKEN, PHONE_ID, TOKEN, WABA_ID, fake_meta


class MetaCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the test server has several databases: as if a dbfilter kept this one
        cls.startClassPatcher(patch.object(type(cls.env['om.whatsapp.account']), '_meta_database_reachable',
                                           return_value=True))
        cls.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://odoo.example.com')
        cls.manager = new_test_user(cls.env, 'om_whatsapp_meta_manager',
                                    groups='base.group_user,base.group_partner_manager,om_whatsapp_base.group_om_whatsapp_manager')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Meta', 'provider': 'meta', 'user_ids': [Command.set(cls.manager.ids)],
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})

    def _setup(self, **values):
        return self.env['om.whatsapp.meta.setup'].with_user(self.manager).create({
            'account_id': self.account.id, 'app_id': APP_ID, 'app_secret': APP_SECRET, 'access_token': TOKEN,
            'test_number': '+32470999999', **values,
        })

    def _connect(self):
        setup = self._setup()
        setup.action_check_token()
        setup.action_connect()
        return setup


@tagged('post_install', '-at_install')
class TestOmWhatsappMetaSetup(MetaCase):

    def test_connect(self):
        """ One value a page, each checked; with the token, Odoo finds the
        number, registers it, sets the webhook on itself, sends a test. """
        with fake_meta() as meta:
            setup = self.env['om.whatsapp.meta.setup'].with_user(self.manager).create(
                {'account_id': self.account.id, 'test_number': '+32470999999'})
            self.assertEqual(setup.step, 'app')
            self.assertEqual(setup.link_create, 'https://developers.facebook.com/apps/creation/')
            self.assertEqual(setup.link_basic, 'https://developers.facebook.com/apps/')
            setup.action_app_created()
            setup.app_id = 'App ID: 12345'
            with self.assertRaisesRegex(UserError, '15 digits'):
                setup.action_check_app_id()
            setup.app_id = f' {APP_ID} '
            setup.action_check_app_id()
            self.assertEqual(setup.step, 'secret')
            self.assertEqual(setup.link_basic, f'https://developers.facebook.com/apps/{APP_ID}/settings/basic/')
            self.assertEqual(setup.link_explorer, 'https://developers.facebook.com/tools/explorer/')
            setup.app_secret = ''
            with self.assertRaisesRegex(UserError, 'Paste the App Secret'):
                setup.action_check_secret()
            setup.app_secret = 'wrong'
            with self.assertRaisesRegex(UserError, 'does not know this App Secret'):
                setup.action_check_secret()
            setup.app_secret = APP_SECRET
            setup.action_check_secret()
            self.assertEqual((setup.step, setup.app_name), ('token', 'Odoo Mates WhatsApp'))
            setup.access_token = TOKEN
            setup.action_check_token()
            # the token reaches two numbers: the user chooses
            self.assertEqual(setup.step, 'number')
            self.assertEqual(setup.number_ids.mapped('phone_number_id'), [PHONE_ID, '5550002222'])
            self.assertEqual(setup.number_id.display_name, '+1 555-000-1111 (Odoo Mates)')
            setup.action_connect()
        account = self.account.sudo()
        self.assertEqual((account.meta_state, account.meta_waba_id, account.meta_phone_number_id),
                         ('connected', WABA_ID, PHONE_ID))
        self.assertEqual((account.phone, account.meta_verified_name, account.meta_waba_name),
                         ('+1 555-000-1111', 'Odoo Mates', 'Odoo Mates Business'))
        self.assertEqual((account.meta_app_id, account.meta_access_token), (APP_ID, TOKEN))
        self.assertTrue(account.meta_token_expires)
        self.assertEqual(meta.registered, {PHONE_ID: account.meta_pin})
        self.assertEqual(len(account.meta_pin), 6)
        self.assertEqual(meta.subscribed, [WABA_ID])
        self.assertEqual(meta.webhook['callback_url'], 'https://odoo.example.com/om_whatsapp/webhook')
        self.assertEqual(meta.webhook['verify_token'], account.meta_verify_token)
        self.assertIn('messages', meta.webhook['fields'])
        self.assertEqual(meta.sent, [{'to': '32470999999', 'type': 'template',
                                      'template': {'name': 'hello_world', 'language': {'code': 'en_US'}}}])
        self.assertEqual(setup.step, 'done')
        self.assertEqual(setup.report.count('✓'), 3)
        self.assertTrue(account.can_send_unattended and account.can_send_batch and account.can_send_files)

    def test_checked_as_pasted(self):
        """ Each value is checked as soon as it is pasted, with what Meta says;
        the stepper follows; the values checked stay on the account. """
        with fake_meta() as meta:
            setup = self.env['om.whatsapp.meta.setup'].with_user(self.manager).create(
                {'account_id': self.account.id, 'test_number': '+32470999999'})
            self.assertIn('o_om_whatsapp_stepper_current"><span class="o_om_whatsapp_stepper_dot">1<', setup.progress)
            setup.app_id = '123'
            setup._onchange_app_id()
            self.assertIn('✗', setup.app_id_check)
            setup.app_id = APP_ID
            setup._onchange_app_id()
            self.assertIn('✓', setup.app_id_check)
            setup.action_check_app_id()
            self.assertEqual(self.account.sudo().meta_app_id, APP_ID)
            self.assertIn('o_om_whatsapp_stepper_done', setup.progress)
            setup.app_secret = 'wrong'
            setup._onchange_app_secret()
            self.assertIn('✗', setup.secret_check)
            setup.app_secret = APP_SECRET
            setup._onchange_app_secret()
            self.assertIn('Odoo Mates WhatsApp', setup.secret_check)
            setup.action_check_secret()
            self.assertEqual(self.account.sudo().meta_app_secret, APP_SECRET)
            setup.access_token = 'expired'
            setup._onchange_access_token()
            self.assertIn('not valid any more', setup.token_check)
            meta.tokens[TOKEN]['app_id'] = '999999999999'
            setup.access_token = TOKEN
            setup._onchange_access_token()
            self.assertIn('made for the app Other App', setup.token_check)
            meta.tokens[TOKEN].pop('app_id')
            setup._onchange_access_token()
            self.assertIn('✓ Valid, with both permissions', setup.token_check)
            meta.numbers.pop()
            setup.action_check_token()
        self.assertEqual(setup.step, 'done')
        self.assertIn('+1 555-000-1111', setup.report)
        self.assertIn('Daily limit: <b>TIER_1K</b>', setup.report)
        self.assertEqual(setup.progress.count('o_om_whatsapp_stepper_done'), 5)

    def test_a_connected_account_keeps_its_app(self):
        """ Trying another app does not touch the App Secret that signs the
        webhook of a connected account, until Connect. """
        self.account.sudo().write({'meta_app_id': '111111111111', 'meta_app_secret': 'live', 'meta_state': 'connected'})
        with fake_meta():
            setup = self._setup()
            setup.action_check_app_id()
            setup.action_check_secret()
        self.assertEqual((self.account.sudo().meta_app_id, self.account.sudo().meta_app_secret), ('111111111111', 'live'))

    def test_one_number_connects_at_once(self):
        with fake_meta() as meta:
            meta.numbers.pop()
            setup = self._setup()
            setup.action_check_token()
        self.assertEqual((setup.step, self.account.meta_state), ('done', 'connected'))

    def test_make_it_permanent(self):
        with fake_meta() as meta:
            self._connect()
            setup = self.env['om.whatsapp.meta.setup'].with_user(self.manager).with_context(
                **self.account.action_meta_permanent_token()['context']).create({})
            self.assertEqual(setup.step, 'permanent')
            setup.access_token = TOKEN
            with self.assertRaisesRegex(UserError, 'expiration Never'):
                setup.action_save_permanent()
            meta.tokens[PERMANENT_TOKEN]['granular_scopes'] = [{'scope': 'whatsapp_business_management', 'target_ids': ['9']}]
            setup.access_token = PERMANENT_TOKEN
            with self.assertRaisesRegex(UserError, 'does not reach the WhatsApp account'):
                setup.action_save_permanent()
            meta.tokens[PERMANENT_TOKEN]['granular_scopes'] = meta.tokens[TOKEN]['granular_scopes']
            setup.action_save_permanent()
        account = self.account.sudo()
        self.assertEqual((account.meta_access_token, account.meta_token_expires), (PERMANENT_TOKEN, False))
        self.assertEqual(account.meta_state, 'connected')

    def test_wrong_credentials_are_told(self):
        with fake_meta() as meta:
            with self.assertRaisesRegex(UserError, 'not valid any more'):
                self._setup(access_token='expired').action_check_token()
            meta.tokens[TOKEN]['scopes'] = ['whatsapp_business_messaging']
            with self.assertRaisesRegex(UserError, 'whatsapp_business_management'):
                self._setup().action_check_token()
            meta.tokens[TOKEN]['app_id'] = '999999999999'
            with self.assertRaisesRegex(UserError, 'made for the app Other App'):
                self._setup().action_check_token()
        self.assertEqual(self.account.meta_state, 'draft')

    def test_token_naming_no_account(self):
        """ A token not limited to some WhatsApp accounts: Meta gives no
        target_ids, so the ID of the account is asked. """
        with fake_meta() as meta:
            meta.tokens[TOKEN]['granular_scopes'] = [{'scope': 'whatsapp_business_management'},
                                                     {'scope': 'whatsapp_business_messaging'}]
            setup = self._setup()
            setup.action_check_token()
            self.assertEqual(setup.step, 'waba')
            setup.waba_id = '999'
            with self.assertRaisesRegex(UserError, 'no WhatsApp account 999'):
                setup.action_check_waba()
            setup.waba_id = f' {WABA_ID} '
            setup.action_check_waba()
            self.assertEqual(setup.step, 'number')
            setup.action_back()
            self.assertEqual(setup.step, 'waba')
            setup.action_connect()
            self.assertEqual(self.account.meta_waba_id, WABA_ID)
            meta.tokens[PERMANENT_TOKEN]['granular_scopes'] = meta.tokens[TOKEN]['granular_scopes']
            setup = self.env['om.whatsapp.meta.setup'].with_user(self.manager).create(
                {'account_id': self.account.id, 'step': 'permanent', 'access_token': PERMANENT_TOKEN,
                 'app_id': APP_ID, 'app_secret': APP_SECRET})
            setup.action_save_permanent()
        self.assertEqual(self.account.sudo().meta_access_token, PERMANENT_TOKEN)

    def test_a_local_odoo_is_told_why_no_message_comes_in(self):
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://localhost:8069')
        with fake_meta() as meta:
            setup = self._connect()
        self.assertIsNone(meta.webhook)
        self.assertEqual(self.account.meta_state, 'error')
        self.assertIn('public https address', self.account.meta_status_message)
        self.assertIn('✗', setup.report)
        # the number works all the same: the test message went
        self.assertEqual(len(meta.sent), 1)

    def test_finish_from_the_account(self):
        """ A local Odoo and a number not yet allowed: connected, with what
        is left told; then Set Webhook and Send Test Message, without
        connecting again. """
        self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://localhost:8069')
        with fake_meta() as meta:
            meta.fail_send = ('(#131030) Recipient phone number not in allowed list', 131030)
            setup = self._connect()
            self.assertTrue(setup.has_problems)
            self.assertIn('Manage phone number list', setup.report)
            with self.assertRaisesRegex(UserError, 'public https address'):
                self.account.action_meta_set_webhook()
            # a tunnel: Odoo may know itself in http, Meta gets https
            self.env['ir.config_parameter'].sudo().set_param('web.base.url', 'http://abc.trycloudflare.com')
            self.env.invalidate_all()
            self.account.with_user(self.manager).action_meta_set_webhook()
            self.assertEqual(meta.webhook['callback_url'], 'https://abc.trycloudflare.com/om_whatsapp/webhook')
            self.assertEqual(self.account.meta_state, 'connected')
            test = self.env['om.whatsapp.meta.setup'].with_user(self.manager).with_context(
                **self.account.action_meta_test_message()['context']).create({'test_number': '+32470999999'})
            self.assertEqual(test.step, 'test')
            with self.assertRaisesRegex(UserError, 'Manage phone number list'):
                test.action_send_test()
            meta.fail_send = None
            test.action_send_test()
        self.assertEqual(meta.sent[-1]['template']['name'], 'hello_world')

    def test_a_number_is_the_number_of_one_account(self):
        """ An archived account gives its number up; an active one keeps it,
        and the user is told which. """
        with fake_meta():
            self._connect()
            second = self.env['om.whatsapp.account'].create({'name': 'Second', 'provider': 'meta'})
            setup = self.env['om.whatsapp.meta.setup'].with_user(self.manager).create({
                'account_id': second.id, 'app_id': APP_ID, 'app_secret': APP_SECRET, 'access_token': TOKEN})
            setup.action_check_token()
            with self.assertRaisesRegex(UserError, 'is the number of the account Meta'):
                setup.action_connect()
            self.account.action_archive()
            setup.action_connect()
        self.assertEqual(second.sudo().meta_phone_number_id, PHONE_ID)
        self.assertEqual((self.account.meta_phone_number_id, self.account.meta_state), (False, 'draft'))

    def test_disconnect_and_delete(self):
        """ Disconnect frees the number; an account with conversations is
        archived, not deleted. """
        with fake_meta():
            self._connect()
        self.account.action_meta_disconnect()
        self.assertEqual((self.account.meta_phone_number_id, self.account.meta_state), (False, 'draft'))
        self.assertEqual(self.account.sudo().meta_app_id, APP_ID)
        self.account._om_whatsapp_receive('+32470123456', 'Hello', 'wamid.x')
        with self.assertRaisesRegex(UserError, 'archive it instead'):
            self.account.unlink()
        empty = self.env['om.whatsapp.account'].create({'name': 'Empty', 'provider': 'meta'})
        empty.unlink()
        self.assertFalse(empty.exists())

    def test_a_server_of_several_databases_is_told(self):
        """ Meta calls without a session: with several databases and no
        dbfilter, Odoo cannot tell which one, and Meta gets a 404. """
        with fake_meta() as meta, patch.object(type(self.account), '_meta_database_reachable', return_value=False):
            setup = self._connect()
            self.assertIsNone(meta.webhook)
            self.assertIn(f'dbfilter = ^{self.env.cr.dbname}$', setup.report)
            with self.assertRaisesRegex(UserError, 'dbfilter'):
                self.account.action_meta_set_webhook()

    def test_check_connection(self):
        with fake_meta() as meta:
            self._connect()
            meta.numbers[0]['quality_rating'] = 'YELLOW'
            self.assertEqual(self.account._meta_check(), [])
            self.assertEqual(self.account.meta_quality_rating, 'YELLOW')
            meta.tokens[TOKEN]['is_valid'] = False
            problems = self.account._meta_check()
        self.assertIn('not valid', problems[0])
        self.assertEqual(self.account.meta_state, 'error')


    def test_secret_only_for_managers(self):
        """ default_get is open to every user: it gives the App Secret only
        to who may change the account. """
        self.account.write({'meta_app_id': APP_ID, 'meta_app_secret': APP_SECRET})
        Setup = self.env['om.whatsapp.meta.setup'].with_context(default_account_id=self.account.id)
        for groups in ('base.group_portal', 'base.group_user', 'base.group_user,om_whatsapp_base.group_om_whatsapp_user'):
            user = new_test_user(self.env, f'om_whatsapp_spy_{len(groups)}', groups=groups)
            with self.assertRaises(AccessError):
                Setup.with_user(user).default_get(['account_id', 'app_id', 'app_secret'])
        values = Setup.with_user(self.manager).default_get(['account_id', 'app_id', 'app_secret'])
        self.assertEqual(values['app_secret'], APP_SECRET)

    def test_meta_buttons_for_managers(self):
        """ The buttons are hidden to users, and closed to them as well: a
        user of the account cannot disconnect its number. """
        self.account.write({'meta_phone_number_id': '1234', 'meta_state': 'connected'})
        user = new_test_user(self.env, 'om_whatsapp_meta_user', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        self.account.user_ids += user
        for method in ('action_meta_disconnect', 'action_meta_check', 'action_meta_set_webhook', 'action_meta_sync_templates'):
            with self.assertRaises(AccessError):
                getattr(self.account.with_user(user), method)()
        self.assertEqual(self.account.meta_phone_number_id, '1234')
        self.account.with_user(self.manager).action_meta_disconnect()
        self.assertFalse(self.account.meta_phone_number_id)

@tagged('post_install', '-at_install')
class TestOmWhatsappMetaSend(MetaCase):

    def _composer(self, **values):
        return self.env['om.whatsapp.composer'].with_user(self.manager).with_context(
            active_model='res.partner', active_ids=self.alice.ids, active_id=self.alice.id,
        ).create({'account_id': self.account.id, 'body': 'Your order is ready', **values})

    def _open_window(self, number='+32470123456'):
        """ The contact writes: free text is allowed for 24 hours. """
        self.account._om_whatsapp_receive(number, 'Hello', f'wamid.in-{number}')

    @staticmethod
    def _messages(meta):
        """ What went to Meta, without the read receipts: on Odoo 17, a reply
        marks the conversation read, as WhatsApp does. """
        return [payload for payload in meta.sent if 'status' not in payload]

    def _notification(self):
        return self.env['mail.notification'].search([
            ('notification_type', '=', 'om_whatsapp'), ('res_partner_id', '=', self.alice.id),
            ('mail_message_id.model', '=', 'res.partner'),
        ], limit=1)

    def test_send_text_and_files(self):
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            meta.sent.clear()
            self._composer().action_send()
            notification = self._notification()
            self.assertEqual(self._messages(meta), [{'to': '32470123456', 'type': 'text',
                                                     'text': {'body': 'Your order is ready', 'preview_url': True}}])
            self.assertEqual(notification.notification_status, 'pending')
            self.assertEqual(notification.mail_message_id.om_whatsapp_id, 'wamid.2')

            meta.sent.clear()
            pdf = self.env['ir.attachment'].with_user(self.manager).create(
                {'name': 'S00012.pdf', 'raw': b'%PDF-1.4', 'res_model': 'om.whatsapp.composer', 'res_id': 0})
            self._composer(body='Your quotation', attachment_ids=[Command.set(pdf.ids)]).action_send()
        self.assertEqual(meta.uploads, ['S00012.pdf'])
        self.assertEqual(meta.sent, [{'to': '32470123456', 'type': 'document',
                                      'document': {'id': 'media-1', 'filename': 'S00012.pdf', 'caption': 'Your quotation'}}])

    def test_an_error_of_meta_is_told(self):
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            meta.fail_send = ('Re-engagement message: more than 24 hours have passed since the customer last replied',
                              131047)
            self._composer().action_send()
        notification = self._notification()
        self.assertEqual(notification.notification_status, 'exception')
        self.assertIn('24 hours', notification.failure_reason)

    def test_reaction(self):
        """ A reaction of a user goes to Meta at once; taken back, an empty emoji. """
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            meta.sent.clear()
            message = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in-+32470123456')], limit=1)
            message = message.with_user(self.manager).sudo()
            message._message_reaction('👍', 'add')
            message._message_reaction('👍', 'remove')
        reaction = {'to': '32470123456', 'recipient_type': 'individual', 'type': 'reaction'}
        self.assertEqual(meta.sent, [
            {**reaction, 'reaction': {'message_id': 'wamid.in-+32470123456', 'emoji': '👍'}},
            {**reaction, 'reaction': {'message_id': 'wamid.in-+32470123456', 'emoji': ''}},
        ])

    def test_reply_quotes_the_message(self):
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            meta.sent.clear()
            received = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in-+32470123456'),
                                                        ('model', '=', 'discuss.channel')], limit=1)
            channel = self.env['discuss.channel'].browse(received.res_id)
            channel.with_user(self.manager).message_post(body='Yes, Friday', message_type='comment', parent_id=received.id)
        self.assertEqual(self._messages(meta)[0]['context'], {'message_id': 'wamid.in-+32470123456'})

    def test_read_receipt(self):
        """ Read in Odoo: Meta marks the last message read; played is read. """
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            meta.sent.clear()
            message = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in-+32470123456')], limit=1)
            message.with_user(self.manager)._om_whatsapp_send_receipts('played')
        self.assertEqual(meta.sent, [{'status': 'read', 'message_id': 'wamid.in-+32470123456'}])
        self.assertEqual(message.om_whatsapp_receipt, 'played')

    def test_not_connected(self):
        with fake_meta() as meta:
            self._open_window()
            self._composer().action_send()
        self.assertFalse(meta.sent)
        self.assertIn('not connected', self._notification().failure_reason)

    def test_automation_sends_from_the_server(self):
        """ Many records, without a user: queued, then the scheduled action
        sends them all. """
        bob = self.env['res.partner'].create({'name': 'Bob', 'phone': '+32470654321'})
        template = self.env['om.whatsapp.template'].create({
            'name': 'Welcome', 'model_id': self.env['ir.model']._get_id('res.partner'), 'body': 'Welcome {{ object.name }}',
        })
        with fake_meta() as meta:
            self._connect()
            self._open_window()
            self._open_window('+32470654321')
            meta.sent.clear()
            with patch.object(type(self.env['ir.cron']), '_trigger') as trigger:
                (self.alice | bob)._message_om_whatsapp_template(template, account=self.account)
            self.assertTrue(trigger.called)
            self.assertFalse(meta.sent)
            self.env['om.whatsapp.account']._cron_meta_send_queue()
        self.assertEqual(sorted(payload['text']['body'] for payload in meta.sent), ['Welcome Alice', 'Welcome Bob'])

    def test_24_hours(self):
        """ Free text within 24 hours of the last message of the contact;
        before, and after, an approved template only. """
        with fake_meta() as meta:
            self._connect()
            with self.assertRaisesRegex(UserError, '24 hours'):
                self._composer().action_send()
            self._open_window()
            channel = self.env['discuss.channel'].search([('om_whatsapp_number', '=', '+32470123456')])
            channel.with_user(self.manager).message_post(body='Yes, tomorrow', message_type='comment')
            channel.om_whatsapp_last_incoming = fields.Datetime.now() - timedelta(hours=25)
            with self.assertRaisesRegex(UserError, '24 hours'):
                channel.with_user(self.manager).message_post(body='Still there?', message_type='comment')
        self.assertEqual([payload['text']['body'] for payload in self._messages(meta)[1:]], ['Yes, tomorrow'])

    def test_window_end_reaches_the_conversation(self):
        """ The end of the 24 hours goes to Discuss, and again when the
        contact writes. """
        with fake_meta():
            self._connect()
            self._open_window()
        channel = self.env['discuss.channel'].search([('om_whatsapp_number', '=', '+32470123456')])
        channel.om_whatsapp_last_incoming = fields.Datetime.now() - timedelta(hours=1)
        until = channel._om_whatsapp_window_values()['om_whatsapp_free_text_until']
        self.assertEqual(until, fields.Datetime.to_string(channel.om_whatsapp_last_incoming + timedelta(hours=24)))
        with patch.object(type(self.env['bus.bus']), '_sendone', autospec=True) as send:
            channel.om_whatsapp_last_incoming = fields.Datetime.now()
        self.assertIn('om_whatsapp_free_text_until', send.call_args.args[3]['Thread'])


@tagged('post_install', '-at_install')
class TestOmWhatsappMetaTemplates(MetaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice.ref = 'C-042'
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'Contact Card', 'model': 'res.partner', 'report_name': 'base.contact_card', 'report_type': 'qweb-pdf',
        })
        cls.template = cls.env['om.whatsapp.template'].create({
            'name': 'Order Confirmed',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'account_id': cls.account.id,
            'report_id': cls.report.id,
            'body': 'Hello {{ object.name }}, your customer code is {{ object.ref }}. Thank you!',
            'meta_footer': 'Odoo Mates',
        })

    def _render_report(self):
        return patch.object(type(self.template), '_om_whatsapp_render_report', return_value=('Card.pdf', b'%PDF-1.4'))

    def test_submit_approve_and_send(self):
        with fake_meta() as meta, self._render_report():
            self._connect()
            self.assertEqual(self.template.meta_name, 'order_confirmed')
            self.template.action_meta_submit()
            submitted = meta.templates[0]
            self.assertEqual((submitted['name'], submitted['language'], submitted['category']),
                             ('order_confirmed', 'en_US', 'UTILITY'))
            header, body, footer = submitted['components']
            self.assertEqual(header, {'type': 'HEADER', 'format': 'DOCUMENT', 'example': {'header_handle': ['handle-1']}})
            self.assertEqual(body['text'], 'Hello {{1}}, your customer code is {{2}}. Thank you!')
            self.assertEqual(len(body['example']['body_text'][0]), 2)
            self.assertEqual(footer, {'type': 'FOOTER', 'text': 'Odoo Mates'})
            self.assertEqual(meta.samples[0][1], f'OAuth {TOKEN}')
            self.assertEqual((self.template.meta_status, self.template.meta_template_id), ('PENDING', 'tpl-1'))

            # Meta approves it, through the webhook
            self.account._meta_process_webhook('message_template_status_update', {
                'event': 'APPROVED', 'message_template_id': 'tpl-1', 'message_template_name': 'order_confirmed',
                'message_template_language': 'en_US', 'reason': 'NONE'})
            self.assertEqual(self.template.meta_status, 'APPROVED')

            # sent as approved: the PDF on top, the values of the contact, outside the 24 hours
            meta.sent.clear()
            composer = self.env['om.whatsapp.composer'].with_user(self.manager).with_context(
                active_model='res.partner', active_ids=self.alice.ids, active_id=self.alice.id,
            ).create({'account_id': self.account.id, 'template_id': self.template.id})
            self.assertTrue(composer.meta_template_ready)
            composer.action_send()
        self.assertEqual(meta.uploads, ['Card.pdf'])
        self.assertEqual(meta.sent, [{'to': '32470123456', 'type': 'template', 'template': {
            'name': 'order_confirmed', 'language': {'code': 'en_US'}, 'components': [
                {'type': 'header', 'parameters': [{'type': 'document', 'document': {'id': 'media-1', 'filename': 'Card.pdf'}}]},
                {'type': 'body', 'parameters': [{'type': 'text', 'text': 'Alice'}, {'type': 'text', 'text': 'C-042'}]},
            ]}}])
        message = self.alice.message_ids.filtered(lambda m: m.message_type == 'om_whatsapp')
        self.assertEqual(message._om_whatsapp_text(), 'Hello Alice, your customer code is C-042. Thank you!')
        self.assertEqual(message.om_whatsapp_status, 'sent')

    def test_what_needs_a_new_approval(self):
        self.template.with_context(om_whatsapp_meta_sync=True).write(
            {'meta_status': 'APPROVED', 'meta_template_id': 'tpl-1', 'meta_waba_id': WABA_ID})
        # another field behind {{2}}: the text of Meta is the same
        self.template.body = 'Hello {{ object.name }}, your customer code is {{ object.email }}. Thank you!'
        self.assertEqual(self.template.meta_status, 'APPROVED')
        self.template.body = 'Hi {{ object.name }}, your customer code is {{ object.email }}.'
        self.assertEqual((self.template.meta_status, self.template.meta_reason), ('draft', 'Changed: submit it again.'))

    def test_meta_refuses_a_text_starting_with_a_field(self):
        self.template.body = '{{ object.name }}, your order is ready'
        with fake_meta():
            self._connect()
            with self.assertRaisesRegex(UserError, 'starts or ends with a field'):
                self.template.action_meta_submit()

    def test_sync(self):
        with fake_meta() as meta, self._render_report():
            self._connect()
            self.template.action_meta_submit()
            meta.templates[0]['status'] = 'REJECTED'
            meta.templates[0]['rejected_reason'] = 'INVALID_FORMAT'
            meta.templates.append({'id': 'tpl-9', 'name': 'shipping_update', 'language': 'en', 'status': 'APPROVED',
                                   'category': 'UTILITY', 'components': [
                                       {'type': 'BODY', 'text': 'Your order {{1}} has shipped on {{2}}.'}]})
            self.assertEqual(self.account._meta_sync_templates(), 1)
        self.assertEqual((self.template.meta_status, self.template.meta_reason), ('REJECTED', 'INVALID_FORMAT'))
        imported = self.env['om.whatsapp.template'].with_context(active_test=False).search([('meta_template_id', '=', 'tpl-9')])
        self.assertFalse(imported.active)
        self.assertEqual(imported.body, "Your order {{ '1' }} has shipped on {{ '2' }}.")
        self.assertEqual(imported.meta_body, 'Your order {{1}} has shipped on {{2}}.')
        self.assertEqual(imported.meta_status, 'APPROVED')

    def test_templates_made_in_meta_come_by_themselves(self):
        """ Meta tells the status of a template it knows and Odoo does not:
        Odoo syncs, and the daily sync catches what the webhook missed. """
        Template = self.env['om.whatsapp.template'].with_context(active_test=False)
        with fake_meta() as meta:
            self._connect()
            meta.templates.append({'id': 'tpl-7', 'name': 'made_in_meta', 'language': 'en', 'status': 'PENDING',
                                   'category': 'UTILITY', 'components': [{'type': 'BODY', 'text': 'Hi {{1}}'}]})
            self.account._meta_process_webhook('message_template_status_update', {
                'event': 'PENDING', 'message_template_id': 'tpl-7', 'message_template_name': 'made_in_meta',
                'message_template_language': 'en', 'reason': 'NONE'})
            self.assertEqual(Template.search([('meta_template_id', '=', 'tpl-7')]).meta_status, 'PENDING')
            meta.templates[0]['status'] = 'APPROVED'
            meta.templates.append({'id': 'tpl-8', 'name': 'missed', 'language': 'en', 'status': 'APPROVED',
                                   'category': 'UTILITY', 'components': [{'type': 'BODY', 'text': 'Bye'}]})
            self.env['om.whatsapp.account']._cron_meta_sync_templates()
            self.assertEqual(Template.search([('meta_template_id', '=', 'tpl-7')]).meta_status, 'APPROVED')
            self.assertTrue(Template.search([('meta_template_id', '=', 'tpl-8')]))
            # Meta not answering stops neither the webhook nor the cron
            with patch.object(MetaApi, 'get_templates', side_effect=MetaApiError('Service temporarily unavailable', 2)):
                self.account._meta_process_webhook('message_template_status_update', {
                    'event': 'APPROVED', 'message_template_id': 'tpl-99'})
                self.env['om.whatsapp.account']._cron_meta_sync_templates()

    def test_preview(self):
        """ The message as WhatsApp shows it: the PDF, the text with the
        samples and its formatting, the footer; the text escaped. """
        self.template.body = 'Hello *{{ object.name }}* <3,\ncode _{{ object.ref }}_'
        self.template._meta_sync_variables()
        self.template.variable_ids.sorted('sequence')[0].sample = 'Alice'
        preview = str(self.template.preview)
        self.assertIn('Contact Card.pdf', preview)
        self.assertIn('Hello <b><span class="o_om_whatsapp_preview_value" title="object.name">Alice</span></b> &lt;3,<br/>',
                      preview)
        self.assertIn('title="object.ref">', preview)
        self.assertIn('<i><span class="o_om_whatsapp_preview_value"', preview)
        self.assertIn('<div class="o_om_whatsapp_preview_footer">Odoo Mates</div>', preview)
        self.template.body = 'Hello {{ object.name'
        self.assertIn('Hello {{ object.name', str(self.template.preview))


@tagged('post_install', '-at_install')
class TestOmWhatsappMetaWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_whatsapp_meta_user', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Meta', 'provider': 'meta', 'user_ids': [Command.set(cls.user.ids)],
            'meta_app_id': APP_ID, 'meta_app_secret': APP_SECRET, 'meta_access_token': TOKEN,
            'meta_waba_id': WABA_ID, 'meta_phone_number_id': PHONE_ID, 'meta_state': 'connected',
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})

    def _post(self, value, field='messages', secret=APP_SECRET):
        body = json.dumps({'object': 'whatsapp_business_account', 'entry': [{
            'id': WABA_ID, 'changes': [{'field': field, 'value': {
                'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': PHONE_ID}, **value}}],
        }]}).encode()
        signature = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.url_open('/om_whatsapp/webhook', data=body, headers={
            'Content-Type': 'application/json', 'X-Hub-Signature-256': signature})

    def _message(self, message, name='Alice A.'):
        return self._post({
            'contacts': [{'wa_id': message['from'], 'profile': {'name': name}}],
            'messages': [{'timestamp': '1760000000', **message}],
        })

    def test_verify(self):
        token = self.account.meta_verify_token
        ok = self.url_open(f'/om_whatsapp/webhook?hub.mode=subscribe&hub.verify_token={token}&hub.challenge=42')
        self.assertEqual((ok.status_code, ok.text), (200, '42'))
        refused = self.url_open('/om_whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42')
        self.assertEqual(refused.status_code, 403)

    def test_only_meta_signs(self):
        response = self._post({'messages': [{'from': '32470123456', 'id': 'wamid.in1', 'type': 'text', 'text': {'body': 'Hi'}}]},
                              secret='forged')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in1')]))

    def test_messages_statuses_and_reactions(self):
        self.assertEqual(self._message({'from': '32470123456', 'id': 'wamid.in1', 'type': 'text',
                                        'text': {'body': 'Is it ready?'}}).status_code, 200)
        incoming = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in1')])
        self.assertEqual((incoming.author_id, incoming._om_whatsapp_text(), incoming.model), (self.alice, 'Is it ready?', 'discuss.channel'))

        # an unknown number, with its WhatsApp name
        self._message({'from': '32470999999', 'id': 'wamid.in2', 'type': 'text', 'text': {'body': 'Who?'}}, name='Zoe')
        channel = self.env['discuss.channel'].search([('om_whatsapp_number', '=', '+32470999999')])
        self.assertEqual(channel.name, 'Zoe (+32470999999)')

        # a picture, downloaded from Meta
        picture = type('Response', (), {'content': b'\xff\xd8jpeg', 'headers': {}, 'raise_for_status': lambda self: None})()
        with fake_meta(), patch('odoo.addons.om_whatsapp.tools.meta_api.requests.get', return_value=picture):
            self._message({'from': '32470123456', 'id': 'wamid.in3', 'type': 'image',
                           'image': {'id': 'media-in-1', 'caption': 'the plan', 'mime_type': 'image/jpeg'},
                           'context': {'id': 'wamid.in1'}})
        image = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.in3')])
        self.assertEqual((image._om_whatsapp_text(), image.attachment_ids.mimetype), ('the plan', 'image/jpeg'))
        self.assertEqual(image.parent_id, incoming)

        # the ticks, and a failure with the words of Meta
        sent = self.env['discuss.channel'].search([('om_whatsapp_partner_id', '=', self.alice.id)])._message_om_whatsapp(
            self.account, 'Yes, tomorrow', '+32470123456', partner=self.alice, status='pending', om_whatsapp_id='wamid.out1')
        self._post({'statuses': [{'id': 'wamid.out1', 'status': 'delivered', 'recipient_id': '32470123456'}]})
        self.assertEqual(sent.om_whatsapp_status, 'delivered')
        self._post({'statuses': [{'id': 'wamid.out1', 'status': 'read', 'recipient_id': '32470123456'}]})
        self.assertEqual(sent.om_whatsapp_status, 'read')
        self._message({'from': '32470123456', 'id': 'wamid.in4', 'type': 'reaction',
                       'reaction': {'message_id': 'wamid.out1', 'emoji': '👍'}})
        self.assertEqual(sent.sudo().reaction_ids.content, '👍')

        failed = self.env['discuss.channel'].search([('om_whatsapp_partner_id', '=', self.alice.id)])._message_om_whatsapp(
            self.account, 'Hello', '+32470123456', partner=self.alice, status='pending', om_whatsapp_id='wamid.out2')
        self._post({'statuses': [{'id': 'wamid.out2', 'status': 'failed', 'errors': [
            {'code': 131026, 'title': 'Message undeliverable', 'error_data': {'details': 'The number is not on WhatsApp'}}]}]})
        self.assertEqual(failed.om_whatsapp_status, 'failed')
        self.assertEqual(failed._om_whatsapp_notifications().failure_reason, 'The number is not on WhatsApp')
