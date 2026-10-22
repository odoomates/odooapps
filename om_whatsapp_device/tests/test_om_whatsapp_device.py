import hashlib
import hmac
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.om_whatsapp_device.models import om_whatsapp_account as device_module

from .fake_bridge import fake_bridge


class DeviceCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, 'om_whatsapp_device_manager',
                                    groups='base.group_user,base.group_partner_manager,om_whatsapp_base.group_om_whatsapp_manager')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Shop', 'provider': 'device', 'user_ids': [Command.set(cls.manager.ids)],
            'device_min_gap': 0, 'device_max_gap': 0,
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})
        # a database where the bridge was started from Odoo: the tests start none
        cls.env['ir.config_parameter'].sudo().set_bool('om_whatsapp_device.autostart', False)

    def _link(self, bridge):
        self.account.with_user(self.manager).action_device_link()
        bridge.link(self.account.device_key)
        self.account.with_user(self.manager).device_link_status()

    def _composer(self, partners=None, **values):
        partners = partners or self.alice
        return self.env['om.whatsapp.composer'].with_user(self.manager).with_context(
            active_model='res.partner', active_ids=partners.ids, active_id=partners[:1].id,
        ).create({'account_id': self.account.id, 'body': 'Your order is ready', **values})

    def _notification(self, partner=None):
        return self.env['mail.notification'].search([
            ('notification_type', '=', 'om_whatsapp'), ('res_partner_id', '=', (partner or self.alice).id),
            ('mail_message_id.model', '=', 'res.partner'),
        ], order='id desc', limit=1)


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceLink(DeviceCase):

    def test_link_with_the_qr_code(self):
        """ The window shows the QR code of the bridge, then linked. """
        with fake_bridge() as bridge:
            action = self.account.with_user(self.manager).action_device_link()
            self.assertEqual((action['tag'], action['params']['account_id']), ('om_whatsapp_device_link', self.account.id))
            config = bridge.sessions[self.account.device_key]['config']
            self.assertEqual(config['database'], self.env.cr.dbname)
            self.assertTrue(config['webhook_url'].endswith('/om_whatsapp_device/webhook'))
            status = self.account.with_user(self.manager).device_link_status()
            self.assertEqual(status['state'], 'linking')
            self.assertEqual(status['qr_image'], 'data:image/png;base64,iVBORw0KGgo=')
            bridge.link(self.account.device_key)
            status = self.account.with_user(self.manager).device_link_status()
        self.assertEqual((status['state'], status['number']), ('linked', '+96555551234'))
        self.assertEqual((self.account.device_state, self.account.phone), ('linked', '+96555551234'))
        self.assertTrue(self.account.can_send_unattended and self.account.can_send_batch and self.account.can_send_files)

    def test_link_with_a_pairing_code(self):
        with fake_bridge() as bridge:
            self.account.with_user(self.manager).action_device_link()
            with self.assertRaisesRegex(UserError, 'country code'):
                self.account.with_user(self.manager).device_link_with_code('123')
            status = self.account.with_user(self.manager).device_link_with_code('+965 5555 1234')
        self.assertEqual((status['state'], status['pairing_code']), ('linking', 'ABCD1234'))
        self.assertEqual(bridge.sessions[self.account.device_key]['config']['pairing_phone'], '96555551234')

    def test_the_bridge_not_running_is_told(self):
        with fake_bridge() as bridge:
            bridge.running = False
            with self.assertRaisesRegex(UserError, 'Start the Bridge'):
                self.account.with_user(self.manager).action_device_link()
            status = self.account.with_user(self.manager).device_link_status()
        self.assertEqual(status['state'], 'offline')
        self.assertEqual(self.account.device_state, 'offline')

    def test_only_managers_link(self):
        user = new_test_user(self.env, 'om_whatsapp_device_user', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        self.account.user_ids = [Command.link(user.id)]
        with fake_bridge(), self.assertRaises(AccessError):
            self.account.with_user(user).action_device_link()

    def test_unlink(self):
        with fake_bridge() as bridge:
            self._link(bridge)
            self.account.with_user(self.manager).action_device_unlink()
        self.assertEqual(self.account.device_state, 'draft')
        self.assertEqual(bridge.sessions[self.account.device_key]['state'], 'logged_out')

    def test_the_secret_is_made_once(self):
        secret = self.account._device_bridge_secret()
        self.assertGreaterEqual(len(secret), 32)
        self.assertEqual(self.account._device_bridge_secret(), secret)
        admin = new_test_user(self.env, 'om_whatsapp_device_admin',
                              groups='base.group_system,om_whatsapp_base.group_om_whatsapp_manager')
        self.assertEqual(self.account.with_user(admin).device_secret, secret)
        # the secret and the address of the bridge: for the administrators of Odoo only
        with self.assertRaises(AccessError):
            self.account.with_user(self.manager).read(['device_secret'])
        with self.assertRaises(AccessError):
            self.account.with_user(self.manager).write({'device_bridge_url': 'http://10.0.0.1:8077'})


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceBridgeProcess(DeviceCase):

    def test_start_the_bridge(self):
        admin = self.env.ref('base.user_admin')
        self.env['ir.config_parameter'].sudo().set_str('om_whatsapp_device.node', False)
        with patch.object(device_module.shutil, 'which', return_value=None), self.assertRaisesRegex(UserError, 'Node.js'):
            self.account.with_user(admin).action_device_start_bridge()
        with patch.object(device_module.shutil, 'which', return_value='/usr/bin/node'), \
             patch.object(device_module, 'BRIDGE_DIR', Path('/nonexistent/bridge')), \
             self.assertRaisesRegex(UserError, 'npm ci'):
            self.account.with_user(admin).action_device_start_bridge()
        with fake_bridge(), patch.object(device_module.shutil, 'which', return_value='/usr/bin/node'), \
             patch.object(Path, 'is_dir', return_value=True), \
             patch.object(device_module.subprocess, 'Popen') as popen:
            self.account.with_user(admin).action_device_start_bridge()
        (command,), options = popen.call_args
        self.assertEqual(command, ['/usr/bin/node', 'src/server.js'])
        self.assertEqual(options['env']['OM_WA_SECRET'], self.account._device_bridge_secret())
        self.assertEqual((options['env']['OM_WA_HOST'], options['env']['OM_WA_PORT']), ('127.0.0.1', '8077'))
        self.assertTrue(options['start_new_session'])
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_bool('om_whatsapp_device.autostart'))
        with self.assertRaises(AccessError):
            self.account.with_user(self.manager).action_device_start_bridge()

    def test_the_check_starts_the_bridge_again(self):
        with fake_bridge() as bridge:
            self._link(bridge)
            bridge.running = False
            self.env['om.whatsapp.account']._cron_device_check()
            self.assertEqual(self.account.device_state, 'offline')
            self.env['ir.config_parameter'].sudo().set_bool('om_whatsapp_device.autostart', True)
            with patch.object(type(self.account), '_device_start_bridge_process') as start:
                self.env['om.whatsapp.account']._cron_device_check()
            self.assertTrue(start.called)
            bridge.running = True
            bridge.sessions[self.account.device_key]['state'] = 'logged_out'
            self.env['om.whatsapp.account']._cron_device_check()
        self.assertEqual(self.account.device_state, 'logged_out')


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceSend(DeviceCase):

    def test_send_text_and_files(self):
        with fake_bridge() as bridge:
            self._link(bridge)
            self._composer().action_send()
            notification = self._notification()
            self.assertEqual(bridge.sent[-1], {'to': '+32470123456', 'text': 'Your order is ready', 'files': []})
            self.assertEqual((notification.notification_status, notification.mail_message_id.om_whatsapp_id),
                             ('pending', 'OUT1'))
            pdf = self.env['ir.attachment'].with_user(self.manager).create(
                {'name': 'S00042.pdf', 'raw': b'%PDF-1.4', 'res_model': 'om.whatsapp.composer', 'res_id': 0})
            self._composer(body='Your quotation', attachment_ids=[Command.set(pdf.ids)]).action_send()
        files = bridge.sent[-1]['files']
        self.assertEqual([(f['name'], f['mimetype'], f['data']) for f in files], [('S00042.pdf', 'application/pdf', 'JVBERi0xLjQ=')])
        self.assertEqual(bridge.sent[-1]['text'], 'Your quotation')

    def test_reaction(self):
        """ A reaction of a user goes through the bridge at once, with the
        key of the message: received here, not sent from this number. """
        with fake_bridge() as bridge:
            self._link(bridge)
            self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'IN1')
            message = self.env['mail.message'].search([('om_whatsapp_id', '=', 'IN1')], limit=1)
            message.with_user(self.manager).sudo()._message_reaction(
                '👍', 'add', self.manager.partner_id, self.env['mail.guest'])
        self.assertEqual(bridge.reactions, [{'to': '+32470123456', 'id': 'IN1', 'from_me': False, 'emoji': '👍'}])
        self.assertFalse(bridge.sent, "a reaction is not a message of the day")

    def test_receipts(self):
        with fake_bridge() as bridge:
            self._link(bridge)
            self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'IN7')
            message = self.env['mail.message'].search([('om_whatsapp_id', '=', 'IN7')], limit=1)
            message.with_user(self.manager)._om_whatsapp_send_receipts('read')
        self.assertEqual(bridge.receipts, [{'to': '+32470123456', 'ids': ['IN7'], 'kind': 'read'}])

    def test_pictures_by_the_scheduled_action(self):
        with fake_bridge() as bridge:
            self._link(bridge)
            bridge.picture = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
            self.account._om_whatsapp_receive('+32470123456', 'Hi', 'IN9')
            self.env['om.whatsapp.account']._cron_om_whatsapp_pictures()
        self.assertEqual(bridge.pictures_asked, ['+32470123456'])
        self.assertTrue(self.alice.image_1920)

    def test_not_linked_and_errors_are_told(self):
        with fake_bridge() as bridge:
            self._composer().action_send()
            self.assertIn('not linked', self._notification().failure_reason)
            self._link(bridge)
            bridge.fail_send = 'This number is not on WhatsApp.'
            self._composer().action_send()
        self.assertEqual(self._notification().failure_reason, 'This number is not on WhatsApp.')

    def test_automation_queues_and_the_day_has_a_limit(self):
        """ Automation rules queue; the queue sends up to the number a day,
        the rest tomorrow. """
        bob = self.env['res.partner'].create({'name': 'Bob', 'phone': '+32470654321'})
        carol = self.env['res.partner'].create({'name': 'Carol', 'phone': '+32470777777'})
        template = self.env['om.whatsapp.template'].create({
            'name': 'Welcome', 'model_id': self.env['ir.model']._get_id('res.partner'), 'body': 'Welcome {{ object.name }}',
        })
        self.account.device_daily_limit = 2
        with fake_bridge() as bridge:
            self._link(bridge)
            with patch.object(type(self.env['ir.cron']), '_trigger') as trigger:
                (self.alice | bob | carol)._message_om_whatsapp_template(template, account=self.account)
            self.assertTrue(trigger.called)
            self.assertFalse(bridge.sent)
            self.env['om.whatsapp.account']._cron_device_send_queue()
            self.assertEqual(sorted(sent['text'] for sent in bridge.sent), ['Welcome Alice', 'Welcome Bob'])
            self.assertEqual(self._notification(carol).notification_status, 'ready')
            # a message by hand, over the limit, is refused with the reason
            self._composer().action_send()
            self.assertIn('messages of the day', self._notification().failure_reason)
            # the next day
            self.env['mail.message'].search([('om_whatsapp_account_id', '=', self.account.id)]).date = \
                fields.Datetime.now() - timedelta(days=1)
            self.env['om.whatsapp.account']._cron_device_send_queue()
        self.assertEqual(bridge.sent[-1]['text'], 'Welcome Carol')


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['om.whatsapp.account'].create({'name': 'Shop', 'provider': 'device', 'device_state': 'linking'})
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})

    def _post(self, items, secret=None):
        body = json.dumps({'key': self.account.device_key, 'items': items}).encode()
        secret = (secret or self.account._device_bridge_secret()).encode()
        signature = 'sha256=' + hmac.new(secret, body, hashlib.sha256).hexdigest()
        return self.url_open('/om_whatsapp_device/webhook', data=body, headers={
            'Content-Type': 'application/json', 'X-Signature-256': signature, 'X-Odoo-Database': self.env.cr.dbname})

    @mute_logger('odoo.addons.om_whatsapp_device.controllers.webhook')
    def test_only_the_bridge_signs(self):
        response = self._post([{'kind': 'state', 'state': 'open', 'me': '96555551234'}], secret='forged-secret')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.account.device_state, 'linking')

    def test_state_messages_statuses_reactions(self):
        self.assertEqual(self._post([{'kind': 'state', 'state': 'open', 'me': '96555551234'}]).status_code, 200)
        self.assertEqual((self.account.device_state, self.account.phone), ('linked', '+96555551234'))
        self._post([
            {'kind': 'message', 'id': 'IN1', 'phone': '32470123456', 'type': 'chat', 'body': 'Is it ready?', 'name': 'Alice A.'},
            {'kind': 'message', 'id': 'IN2', 'phone': '32470123456', 'type': 'ptt', 'body': '',
             'media': {'name': 'voice-message-IN2.ogg', 'mimetype': 'audio/ogg', 'data': 'T2dnUw=='}},
        ])
        incoming = self.env['mail.message'].search([('om_whatsapp_id', '=', 'IN1')])
        self.assertEqual((incoming.author_id, incoming._om_whatsapp_text()), (self.alice, 'Is it ready?'))
        voice = self.env['mail.message'].search([('om_whatsapp_id', '=', 'IN2')])
        self.assertTrue(voice.attachment_ids.voice_ids)

        channel = self.env['discuss.channel'].search([('om_whatsapp_partner_id', '=', self.alice.id)])
        sent = channel._message_om_whatsapp(self.account, 'Yes, tomorrow', '+32470123456', partner=self.alice,
                                            status='pending', om_whatsapp_id='OUT1')
        self._post([{'kind': 'status', 'id': 'OUT1', 'status': 'read'},
                    {'kind': 'reaction', 'id': 'OUT1:32470123456', 'message_id': 'OUT1', 'phone': '32470123456', 'emoji': '👍'}])
        self.assertEqual(sent.om_whatsapp_status, 'read')
        self.assertEqual(sent.sudo().reaction_ids.content, '👍')

        self._post([{'kind': 'state', 'state': 'logged_out', 'reason': 'Unlinked from the phone.'}])
        self.assertEqual(self.account.device_state, 'logged_out')
