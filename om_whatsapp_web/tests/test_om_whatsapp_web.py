from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.addons.om_whatsapp_base.models.om_whatsapp_account import OmWhatsappAccount
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOmWhatsappWeb(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_whatsapp_web_user', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        cls.other = new_test_user(cls.env, 'om_whatsapp_web_other', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Browser',
            'provider': 'web',
            'user_ids': [Command.set(cls.user.ids)],
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})

    def _send(self, **values):
        composer = self.env['om.whatsapp.composer'].with_user(self.user).with_context(
            active_model='res.partner', active_ids=self.alice.ids, active_id=self.alice.id,
        ).create({'account_id': self.account.id, 'body': 'Your order is ready', **values})
        action = composer.action_send()
        notification = self.env['mail.notification'].search([
            ('notification_type', '=', 'om_whatsapp'), ('res_partner_id', '=', self.alice.id),
            ('mail_message_id.model', '=', 'res.partner'),
        ], limit=1)
        return action, notification.with_user(self.user)

    def test_new_accounts_use_the_browser(self):
        self.assertEqual(self.env['om.whatsapp.account'].create({'name': 'New'}).provider, 'web')

    def test_the_browser_sends(self):
        self.assertTrue(self.account.can_send_files)
        self.assertFalse(self.account.can_send_batch)
        attachment = self.env['ir.attachment'].with_user(self.user).create({
            'name': 'order.pdf', 'raw': b'%PDF-1.4', 'res_model': 'om.whatsapp.composer', 'res_id': 0,
        })
        action, notification = self._send(attachment_ids=[Command.set(attachment.ids)])
        message = notification.mail_message_id
        self.assertEqual(action['tag'], 'om_whatsapp_web_send')
        self.assertEqual(action['params']['notification_ids'], notification.ids)
        self.assertEqual(message.om_whatsapp_status, 'queued')
        self.assertEqual(message.attachment_ids, attachment)
        self.assertEqual((attachment.res_model, attachment.res_id), ('res.partner', self.alice.id))
        [payload] = notification.om_whatsapp_web_payload()
        self.assertEqual(notification.notification_status, 'process')
        # another browser open on this Odoo gets nothing to send
        self.assertEqual(notification.om_whatsapp_web_payload(), [])
        self.assertEqual(payload['id'], notification.id)
        self.assertEqual(payload['phone'], '32470123456')
        self.assertEqual(payload['recipient'], 'Alice')
        self.assertEqual(payload['body'], 'Your order is ready')
        self.assertEqual(payload['attachments'], [{'id': attachment.id, 'name': 'order.pdf', 'mimetype': 'application/pdf'}])

        notification.om_whatsapp_web_done(whatsapp_id='3EB0AB')
        self.assertEqual(message.om_whatsapp_status, 'sent')
        self.assertEqual(message.om_whatsapp_id, '3EB0AB')
        # a late answer changes nothing
        notification.om_whatsapp_web_done(error='late')
        self.assertEqual(message.om_whatsapp_status, 'sent')

    def test_the_extension_reports_an_error(self):
        _action, notification = self._send()
        notification.om_whatsapp_web_payload()
        notification.om_whatsapp_web_done(error='Not on WhatsApp')
        self.assertEqual((notification.notification_status, notification.failure_reason), ('exception', 'Not on WhatsApp'))
        action = notification.mail_message_id.action_om_whatsapp_retry()
        self.assertEqual(action['tag'], 'om_whatsapp_web_send')
        self.assertEqual(notification.notification_status, 'ready')

    def test_cancel(self):
        _action, notification = self._send()
        notification.om_whatsapp_web_cancel()
        self.assertEqual(notification.notification_status, 'canceled')

    def test_fallback_on_whatsapp_web(self):
        _action, notification = self._send()
        action = notification.om_whatsapp_web_fallback()
        self.assertEqual(action['url'], 'https://web.whatsapp.com/send?phone=32470123456&text=Your%20order%20is%20ready')
        self.assertEqual(notification.notification_status, 'pending')

    def test_only_the_account_users(self):
        _action, notification = self._send()
        with self.assertRaises(UserError):
            notification.with_user(self.other).om_whatsapp_web_payload()

    # ------------------------------------------------------------
    # RECEIVING
    # ------------------------------------------------------------

    def _accept(self, me, items):
        return self.env['om.whatsapp.account'].with_user(self.user).om_whatsapp_web_accept(me, items)

    def _receive(self, me, items):
        return self.env['om.whatsapp.account'].with_user(self.user).om_whatsapp_web_receive(me, items)

    def test_accept_only_known_numbers(self):
        items = [
            {'kind': 'message', 'id': 'A1', 'phone': '32470123456'},
            {'kind': 'message', 'id': 'B2', 'phone': '32470999999'},
        ]
        self.assertEqual(self._accept('32470000000', items), {'account': True, 'accept': ['A1', 'B2']})
        self.account.receive_unknown = False
        self.assertEqual(self._accept('32470000000', items), {'account': True, 'accept': ['A1']})
        # once the account has its number, another WhatsApp is never read into it
        self.account.phone = '+32 470 00 00 00'
        self.assertEqual(self._accept('32470000000', items)['account'], True)
        self.assertEqual(self._accept('32471111111', items), {'account': False, 'accept': []})
        self.assertEqual(self.env['om.whatsapp.account'].with_user(self.other).om_whatsapp_web_accept('32470000000', items),
                         {'account': False, 'accept': []})

    def test_only_messages_since_the_account_started(self):
        """ The extension keeps what it read for any Odoo: a new database gets
        the messages from its first connection on, not the old chats. """
        with freeze_time('2026-10-20 10:00:00'):
            self.env['om.whatsapp.account'].with_user(self.user).om_whatsapp_web_status('32470000000')
        self.assertEqual(str(self.account.om_whatsapp_web_since), '2026-10-20 10:00:00')
        old = 1792490400 - 3600  # 09:00 UTC
        new = 1792490400 + 30  # 10:00:30 UTC
        items = [
            {'kind': 'message', 'id': 'OLD', 'phone': '32470123456', 'body': 'from before', 't': old},
            {'kind': 'message', 'id': 'NEW', 'phone': '32470123456', 'body': 'from now', 't': new},
        ]
        self.assertEqual(self._accept('32470000000', items)['accept'], ['NEW'])
        self.assertEqual(self._receive('32470000000', items), 1)
        received = self.env['mail.message'].search([('om_whatsapp_id', 'in', ['OLD', 'NEW'])])
        self.assertEqual(set(received.mapped('om_whatsapp_id')), {'NEW'})

    def test_started_account_keeps_its_backlog(self):
        """ An account connected before the start was recorded starts from its
        last connection: what came since then still comes. """
        self.account.om_whatsapp_web_seen = '2026-10-20 08:00:00'
        item = {'kind': 'message', 'id': 'MID', 'phone': '32470123456', 'body': 'while away', 't': 1792490400 - 3600}
        self.assertEqual(self._accept('32470000000', [item])['accept'], ['MID'])
        self.assertEqual(str(self.account.om_whatsapp_web_since), '2026-10-20 08:00:00')

    def test_receive_messages_files_and_status(self):
        _action, notification = self._send()
        notification.om_whatsapp_web_payload()
        notification.om_whatsapp_web_done(whatsapp_id='S1')
        count = self._receive('32470000000', [
            {'kind': 'message', 'id': 'A1', 'phone': '32470123456', 'body': 'Here is the plan', 'quoted_id': 'S1',
             'media': {'name': 'plan.pdf', 'mimetype': 'application/pdf', 'data': 'JVBERi0xLjQ='}},
            {'kind': 'message', 'id': 'A2', 'phone': '32470123456', 'note': 'Voice message', 'body': ''},
            {'kind': 'message', 'id': 'A3', 'phone': '32470123456', 'body': 'photo', 'media_error': 'The file is too big.'},
            {'kind': 'status', 'id': 'S1', 'ack': 3},
            {'kind': 'reaction', 'id': 'S1:32470123456', 'message_id': 'S1', 'phone': '32470123456', 'emoji': '👍'},
            {'kind': 'message', 'id': 'A4', 'phone': '32470999999', 'body': 'unknown', 'name': 'Zoe'},
            {'kind': 'message', 'id': 'A5', 'phone': '32470123456', 'type': 'ptt', 'body': '',
             'media': {'name': 'voice-message-A5.ogg', 'mimetype': 'audio/ogg', 'data': 'T2dnUw=='}},
            {'kind': 'message', 'id': 'A6', 'phone': '32470123456', 'type': 'sticker', 'body': '', 'media_error': 'gone'},
        ])
        self.assertEqual(count, 8)
        messages = self.alice.message_ids.filtered(lambda m: m.om_whatsapp_id in ('A1', 'A2', 'A3')).sorted('id')
        self.assertEqual(messages.mapped('om_whatsapp_status'), ['received'] * 3)
        self.assertEqual((messages[0].attachment_ids.name, messages[0].attachment_ids.file_size), ('plan.pdf', 8))
        self.assertEqual(messages[1]._om_whatsapp_text(), '[Voice message]')
        self.assertIn('The file is too big.', messages[2]._om_whatsapp_text())
        self.assertEqual(notification.mail_message_id.om_whatsapp_status, 'read')
        self.assertEqual(notification.sudo().mail_message_id.reaction_ids.content, '👍')
        unknown = self.env['mail.message'].search([('om_whatsapp_id', '=', 'A4')])
        self.assertEqual(unknown.email_from, 'Zoe (+32470999999)')
        voice = self.env['mail.message'].search([('om_whatsapp_id', '=', 'A5'), ('model', '=', 'discuss.channel')])
        self.assertTrue(voice.attachment_ids.voice_ids)
        sticker = self.env['mail.message'].search([('om_whatsapp_id', '=', 'A6'), ('model', '=', 'discuss.channel')])
        self.assertTrue(sticker._om_whatsapp_text().startswith('[Sticker]'))

    def test_done_only_for_a_message_taken(self):
        _action, notification = self._send()
        with self.assertRaises(UserError):
            notification.om_whatsapp_web_done()

    def test_the_phone_copy_of_a_message_sent_by_odoo(self):
        """ The reader sees the message Odoo sent before the extension gives
        its id, while the browser still sends it: it is the same message,
        not one sent from the phone. """
        _action, notification = self._send()
        notification.om_whatsapp_web_payload()
        self._receive('32470000000', [
            {'kind': 'message', 'id': 'S9', 'phone': '32470123456', 'from_me': True, 'body': 'Your order is ready'},
            {'kind': 'message', 'id': 'P1', 'phone': '32470123456', 'from_me': True, 'body': 'Typed on the phone'},
        ])
        message = notification.mail_message_id
        self.assertEqual((message.om_whatsapp_id, message.om_whatsapp_status), ('S9', 'sent'))
        # then the extension answers
        notification.om_whatsapp_web_done(whatsapp_id='S9')
        self.assertEqual(len(self.env['mail.message'].search([('om_whatsapp_id', '=', 'S9')])), 2)  # order and conversation
        phone = self.alice.message_ids.filtered(lambda m: m.om_whatsapp_id == 'P1')
        self.assertEqual((phone.author_id, phone.om_whatsapp_status), (self.user.partner_id, 'sent'))

    # ------------------------------------------------------------
    # AUTOMATION
    # ------------------------------------------------------------

    def _automate(self, partners, at_screen):
        template = self.env['om.whatsapp.template'].create({
            'name': 'Welcome', 'model_id': self.env['ir.model']._get_id('res.partner'), 'body': 'Welcome {{ object.name }}',
        })
        with patch.object(OmWhatsappAccount, '_om_whatsapp_user_at_screen', return_value=at_screen):
            partners.with_user(self.user)._message_om_whatsapp_template(template, account=self.account)
        return self.env['mail.notification'].search([
            ('notification_type', '=', 'om_whatsapp'), ('res_partner_id', 'in', partners.ids),
            ('mail_message_id.model', '=', 'res.partner'),
        ])

    def test_reaction_goes_through_the_browser(self):
        """ A reaction of a user in Odoo: their browser reacts in WhatsApp Web. """
        self._send()
        message = self.env['mail.message'].search([('model', '=', 'res.partner'), ('res_id', '=', self.alice.id),
                                                   ('message_type', '=', 'om_whatsapp')], limit=1)
        message.om_whatsapp_id = '3EB0AB'
        with patch.object(type(self.env.user), '_bus_send', autospec=True) as bus_send:
            message.with_user(self.user).sudo()._message_reaction('👍', 'add', self.user.partner_id, self.env['mail.guest'])
        (user, kind, payload), _kwargs = bus_send.call_args
        self.assertEqual((user, kind), (self.user, 'om_whatsapp/action'))
        self.assertEqual(payload['action']['tag'], 'om_whatsapp_web_react')
        self.assertEqual(payload['action']['params'], {'phone': '32470123456', 'whatsapp_id': '3EB0AB', 'emoji': '👍'})

    def test_status_records_the_last_connection(self):
        """ The pages tell the number linked in WhatsApp Web: its account
        records who was connected and when, at most once a minute. """
        Account = self.env['om.whatsapp.account'].with_user(self.user)
        self.account.phone = '+32 470 00 00 00'
        self.assertEqual(Account.om_whatsapp_web_status(False), {'has_account': True, 'account': False})
        self.assertFalse(self.account.om_whatsapp_web_seen)

        answer = Account.om_whatsapp_web_status('32470000000')
        self.assertEqual(answer['account'], {'id': self.account.id, 'name': 'Browser', 'phone': '+32 470 00 00 00'})
        self.assertEqual(self.account.om_whatsapp_web_seen_user_id, self.user)
        seen = self.account.om_whatsapp_web_seen
        self.assertTrue(seen)
        with freeze_time(seen + timedelta(seconds=30)):
            Account.om_whatsapp_web_status('32470000000')
            self.assertEqual(self.account.om_whatsapp_web_seen, seen, "not written again within a minute")
        with freeze_time(seen + timedelta(seconds=90)):
            Account.om_whatsapp_web_status('32470000000')
            self.assertGreater(self.account.om_whatsapp_web_seen, seen)

        self.assertFalse(Account.om_whatsapp_web_status('32470999999')['account'], "another number is no account")
        stranger = self.env['om.whatsapp.account'].with_user(self.other)
        self.assertEqual(stranger.om_whatsapp_web_status('32470000000'), {'has_account': False, 'account': False})

    def test_receipt_goes_through_the_browser(self):
        self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', '3EB0R1')
        message = self.env['mail.message'].search([('om_whatsapp_id', '=', '3EB0R1')], limit=1)
        with patch.object(type(self.env.user), '_bus_send', autospec=True) as bus_send:
            message.with_user(self.user)._om_whatsapp_send_receipts('read')
        (user, kind, payload), _kwargs = bus_send.call_args
        self.assertEqual((user, kind, payload['action']['tag']), (self.user, 'om_whatsapp/action', 'om_whatsapp_web_receipt'))
        self.assertEqual(payload['action']['params'], {'phone': '32470123456', 'ids': ['3EB0R1'], 'kind': 'read'})

    def test_pictures_read_by_the_browser(self):
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        self.account.phone = '+32 470 00 00 00'
        Account = self.env['om.whatsapp.account'].with_user(self.user)
        self.account._om_whatsapp_receive('+32470123456', 'Hi', '3EB0P1')
        self.assertEqual(Account.om_whatsapp_web_pictures_due('32470000000'), ['32470123456'])
        self.assertEqual(Account.om_whatsapp_web_pictures_due('32470999999'), [], "another WhatsApp")
        self.assertTrue(Account.om_whatsapp_web_set_picture('32470000000', '32470123456', data=png))
        self.assertTrue(self.alice.image_1920)
        self.assertEqual(Account.om_whatsapp_web_pictures_due('32470000000'), [])

    def test_picture_downloaded_from_whatsapp_only(self):
        Account = self.env['om.whatsapp.account']
        with patch('odoo.addons.om_whatsapp_web.models.om_whatsapp_account.requests.get') as get:
            get.return_value.raw.read.return_value = b'\x89PNG'
            self.assertTrue(Account._om_whatsapp_web_download_picture('https://pps.whatsapp.net/v/t61/photo.jpg?oe=1'))
            self.assertFalse(Account._om_whatsapp_web_download_picture('https://evil.example.com/photo.jpg'))
            self.assertFalse(Account._om_whatsapp_web_download_picture('http://pps.whatsapp.net/photo.jpg'))
            self.assertFalse(Account._om_whatsapp_web_download_picture('https://whatsapp.net.evil.com/photo.jpg'))
        self.assertEqual(get.call_count, 1)

    def test_automation_from_the_click_of_a_user(self):
        """ An order confirmed by a user: their browser sends the message. """
        with patch.object(type(self.env.user), '_bus_send', autospec=True) as bus_send:
            notification = self._automate(self.alice, at_screen=True)
        self.assertEqual(notification.notification_status, 'ready')
        (_user, kind, payload), _kwargs = bus_send.call_args
        self.assertEqual(kind, 'om_whatsapp/action')
        self.assertEqual(payload['action']['params']['notification_ids'], notification.ids)

    def test_automation_without_a_user_does_not_send(self):
        bob = self.env['res.partner'].create({'name': 'Bob', 'phone': '+32470654321'})
        notifications = self._automate(self.alice | bob, at_screen=True)
        self.assertEqual(set(notifications.mapped('notification_status')), {'exception'})
        notification = self._automate(self.alice, at_screen=False)[-1:]
        self.assertIn('not by itself', notification.failure_reason)
