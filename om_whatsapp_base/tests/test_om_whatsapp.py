from datetime import timedelta
from unittest.mock import patch
from urllib.parse import quote

from odoo import Command, fields
from odoo.addons.om_whatsapp_base.models.om_whatsapp_account import OmWhatsappAccount
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


def _batch_with_files(accounts):
    for account in accounts:
        account.can_send_files = True
        account.can_send_batch = True
        account.can_send_unattended = False


def _from_server(accounts):
    """ A provider that sends from the server, as Meta does. """
    for account in accounts:
        account.can_send_files = True
        account.can_send_batch = True
        account.can_send_unattended = True


@tagged('post_install', '-at_install')
class TestOmWhatsapp(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_whatsapp_user',
                                 groups='base.group_user,base.group_partner_manager,om_whatsapp_base.group_om_whatsapp_user')
        cls.other = new_test_user(cls.env, 'om_whatsapp_other', groups='base.group_user,om_whatsapp_base.group_om_whatsapp_user')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Sales',
            'provider': 'link',
            'user_ids': [Command.set(cls.user.ids)],
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})
        cls.bob = cls.env['res.partner'].create({'name': 'Bob', 'phone': '+32470654321'})
        cls.nophone = cls.env['res.partner'].create({'name': 'No Phone'})
        cls.template = cls.env['om.whatsapp.template'].create({
            'name': 'Hello',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'body': 'Hello {{ object.name }}',
        })

    def _composer(self, partners, **values):
        return self.env['om.whatsapp.composer'].with_user(self.user).with_context(
            active_model='res.partner', active_ids=partners.ids, active_id=partners[:1].id,
        ).create({'account_id': self.account.id, **values})

    def _notifications(self, partners):
        """ Those of the documents, not of their copies in the conversations. """
        return self.env['mail.notification'].search([
            ('notification_type', '=', 'om_whatsapp'), ('res_partner_id', 'in', partners.ids),
            ('mail_message_id.model', '!=', 'discuss.channel'),
        ])

    def _channel(self, number='+32470123456'):
        return self.env['discuss.channel'].search([
            ('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.account.id),
            ('om_whatsapp_number', '=', number),
        ])

    def _post(self, document, body='Hi', partner=None, number='+32470123456'):
        return document._message_om_whatsapp(self.account, body, number, partner=partner or document)

    def test_click_to_chat_opens_the_chat(self):
        composer = self._composer(self.alice, template_id=self.template.id)
        self.assertEqual(composer.number, '+32470123456')
        self.assertEqual(composer.body, 'Hello Alice')
        action = composer.action_send()
        self.assertEqual(action['url'], f"https://wa.me/32470123456?text={quote('Hello Alice')}")
        notification = self._notifications(self.alice)
        self.assertEqual(notification.notification_status, 'pending')
        self.assertEqual(notification.om_whatsapp_number, '+32470123456')
        message = notification.mail_message_id
        self.assertEqual((message.model, message.res_id, message.message_type), ('res.partner', self.alice.id, 'om_whatsapp'))
        self.assertEqual(message.om_whatsapp_status, 'sent')
        self.assertEqual(message.author_id, self.user.partner_id)
        self.assertEqual(message.om_whatsapp_account_id, self.account)
        self.assertEqual(message._om_whatsapp_text(), 'Hello Alice')
        self.assertEqual(self.alice.om_whatsapp_message_count, 1)
        self.assertEqual(message.display_name, 'WhatsApp to Alice')

    def test_text_is_sent_as_typed(self):
        text = 'Hello Alice,\n\nyour order: https://example.com/my/orders/1?a=1&b=2\n<b>not bold</b>'
        message = self._post(self.alice, text)
        self.assertEqual(message._om_whatsapp_text(), text)

    def test_number_of_the_phone_field(self):
        Composer = self.env['om.whatsapp.composer'].with_user(self.user).with_context(
            active_model='res.partner', active_ids=self.alice.ids, om_whatsapp_number='+32470999888',
        )
        self.assertEqual(Composer.create({'account_id': self.account.id}).number, '+32470999888')
        form = Form(Composer)
        self.assertEqual(form.number, '+32470999888')
        self.assertEqual(form.partner_id, self.alice)

    def test_click_to_chat_sends_one_at_a_time(self):
        with self.assertRaises(UserError):
            self._composer(self.alice | self.bob, template_id=self.template.id).action_send()

    def test_single_without_number_is_not_posted(self):
        with self.assertRaises(UserError):
            self._composer(self.nophone, body='Hi', number=False).action_send()

    def test_batch_renders_each_record_and_skips(self):
        self.env['phone.blacklist'].sudo().create({'number': '+32470654321'})
        with patch.object(OmWhatsappAccount, '_compute_capabilities', _batch_with_files), \
             patch.object(OmWhatsappAccount, '_om_whatsapp_send_link', autospec=True) as send:
            composer = self._composer(self.alice | self.bob | self.nophone, template_id=self.template.id)
            self.assertEqual((composer.recipient_valid_count, composer.recipient_invalid_count), (2, 1))
            composer.action_send()
        queued = send.call_args.args[1]
        self.assertEqual(queued.res_partner_id, self.alice)
        self.assertEqual(queued.mail_message_id._om_whatsapp_text(), 'Hello Alice')
        bob = self._notifications(self.bob)
        self.assertEqual((bob.notification_status, bob.failure_type), ('canceled', 'om_whatsapp_optout'))
        nophone = self.nophone.message_ids.filtered(lambda m: m.message_type == 'om_whatsapp')
        self.assertEqual(nophone.om_whatsapp_status, 'failed')
        self.assertTrue(nophone.has_om_whatsapp_error)
        # the Failed filter of WhatsApp > Messages
        Message = self.env['mail.message']
        self.assertIn(nophone, Message.search([('has_om_whatsapp_error', '=', True)]))
        self.assertNotIn(nophone, Message.search([('has_om_whatsapp_error', '=', False)]))
        self.assertIn(queued.mail_message_id, Message.search([('has_om_whatsapp_error', '!=', True)]))

    def test_status_never_moves_back(self):
        message = self._post(self.alice)
        notification = message._om_whatsapp_notifications()
        self.assertEqual(message.om_whatsapp_status, 'queued')
        notification._om_whatsapp_set_status('delivered')
        notification._om_whatsapp_set_status('sent')
        self.assertEqual(message.om_whatsapp_status, 'delivered')
        notification._om_whatsapp_set_status('read')
        self.assertEqual(message.om_whatsapp_status, 'read')
        notification._om_whatsapp_set_status('delivered')
        notification._om_whatsapp_set_status('failed', 'late error')
        self.assertEqual(message.om_whatsapp_status, 'read')

    def test_read_is_not_tracked_for_users(self):
        message = self._post(self.alice, partner=self.other.partner_id)
        notification = message._om_whatsapp_notifications()
        self.assertTrue(notification.is_read)
        self.assertEqual(message.om_whatsapp_status, 'queued')
        notification._om_whatsapp_set_status('read')
        self.assertEqual(message.om_whatsapp_status, 'queued')

    def test_retry_and_cancel(self):
        message = self._post(self.alice)
        message._om_whatsapp_notifications()._om_whatsapp_set_status('failed', 'Not on WhatsApp')
        self.assertEqual(message._om_whatsapp_notifications().failure_reason, 'Not on WhatsApp')
        action = message.with_user(self.user).action_om_whatsapp_retry()
        self.assertTrue(action['url'].startswith('https://wa.me/32470123456'))
        self.assertEqual(message.om_whatsapp_status, 'sent')
        with self.assertRaises(UserError):
            message.action_om_whatsapp_retry()
        queued = self._post(self.alice)
        queued.action_om_whatsapp_cancel()
        self.assertEqual(queued.om_whatsapp_status, 'cancel')

    def test_whatsapp_is_not_mailed(self):
        """ The followers of the document who are users get a reply in their
        Inbox, never by email; the customer has it in WhatsApp. """
        order = self.env['res.partner'].create({'name': 'S00012'})
        self.other.notification_type = 'email'
        order.message_subscribe(partner_ids=(self.other.partner_id | self.bob).ids)
        self._post(order, partner=self.alice)._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.1')
        reply = order.message_ids.filtered(lambda m: m.om_whatsapp_id == 'wamid.1')
        self.assertEqual(reply.notification_ids.mapped('notification_type'), ['inbox'])
        self.assertEqual(reply.notification_ids.res_partner_id, self.other.partner_id)

    def test_receive_in_the_conversation_once(self):
        """ A message of a contact goes to the conversation with its number;
        with no document to answer, only there. """
        incoming = self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.1',
                                                     attachments=[('photo.txt', b'data')])
        again = self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.1')
        self.assertEqual(again, incoming)
        channel = self._channel()
        self.assertEqual((incoming.model, incoming.res_id), ('discuss.channel', channel.id))
        self.assertEqual((incoming.author_id, incoming.message_type), (self.alice, 'om_whatsapp'))
        self.assertEqual(incoming.om_whatsapp_status, 'received')
        self.assertEqual(incoming.display_name, 'WhatsApp from Alice')
        self.assertEqual(incoming.attachment_ids.res_model, 'discuss.channel')
        self.assertFalse(self.alice.message_ids.filtered(lambda m: m.message_type == 'om_whatsapp'))
        self.assertEqual((channel.name, channel.om_whatsapp_partner_id, channel.om_whatsapp_account_id),
                         ('Alice', self.alice, self.account))
        self.assertEqual(channel.channel_member_ids.partner_id, self.user.partner_id | self.alice)

    def test_unknown_number(self):
        """ An unknown number opens a conversation named by its number and
        WhatsApp name, where a contact is made; or it is not kept. """
        message = self.account._om_whatsapp_receive('+32470999999', 'Who?', 'wamid.2', profile_name='Zoe')
        channel = self._channel('+32470999999')
        self.assertEqual((channel.name, channel.om_whatsapp_partner_id), ('Zoe (+32470999999)', self.env['res.partner']))
        self.assertEqual((message.author_id, message.email_from), (self.env['res.partner'], 'Zoe (+32470999999)'))
        self.assertEqual(channel.channel_member_ids.partner_id, self.user.partner_id)
        answer = channel.with_user(self.user).message_post(body='Hello Zoe', message_type='comment')

        action = channel.with_user(self.user).om_whatsapp_action_create_contact()
        self.assertEqual((action['context']['default_name'], action['context']['default_phone']), ('Zoe', '+32470999999'))
        zoe = self.env['res.partner'].with_user(self.user).with_context(action['context']).create({
            'name': 'Zoe Martin', 'phone': '+32470999999',
        })
        self.assertEqual((channel.om_whatsapp_partner_id, channel.name), (zoe, 'Zoe Martin'))
        self.assertIn(zoe, channel.channel_member_ids.partner_id)
        self.assertEqual(message.author_id, zoe)
        self.assertEqual(answer._om_whatsapp_notifications().res_partner_id, zoe)

        self.account.receive_unknown = False
        self.assertFalse(self.account._om_whatsapp_receive('+32470888888', 'Hi', 'wamid.8'))
        self.assertFalse(self._channel('+32470888888'))
        self.assertTrue(self.account._om_whatsapp_receive('+32470123456', 'Hi', 'wamid.9'))

    def test_reply_in_the_conversation(self):
        """ A message quoting another is its answer in the conversation. """
        first = self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.1')
        reply = self.account._om_whatsapp_receive('+32470123456', 'Hello?', 'wamid.2', quoted_id='wamid.1')
        self.assertEqual(reply.parent_id, first)

    def test_voice_message(self):
        message = self.account._om_whatsapp_receive('+32470123456', '', 'wamid.1',
                                                     attachments=[('voice-message.ogg', b'OggS')], voice=True)
        self.assertTrue(message.attachment_ids.voice_ids)

    def test_receipts_read_in_discuss_and_played(self):
        """ A user who reads the conversation tells WhatsApp the messages of
        the contact were read, once; a voice message played in Odoo, played.
        Not the messages sent from Odoo, nor for someone outside the account. """
        self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.r1')
        voice = self.account._om_whatsapp_receive('+32470123456', '', 'wamid.r2',
                                                  attachments=[('voice-message.ogg', b'OggS')], voice=True)
        channel = self._channel()
        channel.with_user(self.user).message_post(body='Yes, today', message_type='comment')
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == self.user.partner_id)
        last = self.env['mail.message'].search([('model', '=', 'discuss.channel'), ('res_id', '=', channel.id)],
                                               order='id desc', limit=1)
        with patch.object(OmWhatsappAccount, '_om_whatsapp_receipt_link', create=True, return_value=None) as receipt:
            member.with_user(self.user)._mark_as_read(last.id)
            member.with_user(self.user)._mark_as_read(last.id)
            self.env['mail.message'].with_user(self.user).om_whatsapp_played(voice.attachment_ids[:1].id)
            self.env['mail.message'].with_user(self.user).om_whatsapp_played(voice.attachment_ids[:1].id)
        self.assertEqual([(call.args[0], sorted(call.args[1]), call.args[2]) for call in receipt.call_args_list], [
            ('+32470123456', ['wamid.r1', 'wamid.r2'], 'read'),
            ('+32470123456', ['wamid.r2'], 'played'),
        ])
        copies = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.r2')])
        self.assertEqual(set(copies.mapped('om_whatsapp_receipt')), {'played'})

        self.account._om_whatsapp_receive('+32470123456', 'And the chairs?', 'wamid.r3')
        with patch.object(OmWhatsappAccount, '_om_whatsapp_receipt_link', create=True) as receipt:
            stranger = channel.channel_member_ids.filtered(lambda m: m.partner_id == self.other.partner_id)
            if not stranger:
                channel._add_members(partners=self.other.partner_id, post_joined_message=False)
                stranger = channel.channel_member_ids.filtered(lambda m: m.partner_id == self.other.partner_id)
            stranger.with_user(self.other)._mark_as_read(channel.message_ids[:1].id)
        receipt.assert_not_called()

    def test_profile_pictures_only_without_a_photo(self):
        """ The picture of a customer with a photo in Odoo is never looked
        for; one without gets it as photo, once; an unknown number gets it on
        its conversation, which gives it to the contact made from it. """
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        self.account.receive_unknown = True
        self.alice.image_1920 = png
        self.account._om_whatsapp_receive('+32470123456', 'Hi', 'wamid.p1')
        self.account._om_whatsapp_receive('+32470654321', 'Hi', 'wamid.p2')
        self.account._om_whatsapp_receive('+32470555555', 'Hi', 'wamid.p3')
        due = self.account._om_whatsapp_pictures_due(limit=10)
        self.assertEqual(sorted(due.mapped('om_whatsapp_number')), ['+32470555555', '+32470654321'], "not Alice")

        self.assertTrue(self.account._om_whatsapp_set_picture('+32470654321', png))
        self.assertTrue(self.bob.image_1920, "Bob had no photo")
        self.assertEqual(self._channel('+32470654321').with_user(self.user).avatar_128, self.bob.image_128,
                         "his conversation shows it")
        self.assertNotIn(self._channel('+32470654321'), self.account._om_whatsapp_pictures_due(limit=10))
        alice_photo = str(self.alice.image_1920)
        self.account._om_whatsapp_set_picture('+32470123456', png)
        self.assertEqual(str(self.alice.image_1920), alice_photo, "a photo set in Odoo is never replaced")

        unknown = self._channel('+32470555555')
        self.account._om_whatsapp_set_picture('+32470555555', png)
        self.assertTrue(unknown.image_128)
        self.assertNotIn(unknown, self.account._om_whatsapp_pictures_due(limit=10), "looked for this week")
        lumber = self.env['res.partner'].create({'name': 'Lumber Inc', 'phone': '+32470555555'})
        unknown._om_whatsapp_link_partner(lumber)
        self.assertTrue(lumber.image_1920)
        self.assertFalse(unknown.image_128, "the conversation shows the contact now")
        self.assertEqual(unknown.avatar_128, lumber.image_128)

        self.account.fetch_pictures = False
        self.assertFalse(self.account._om_whatsapp_pictures_due(limit=10))

    def test_reply_quotes_the_message_it_answers(self):
        """ A reply in Discuss to a message of the contact, or to one sent
        from Odoo, tells the provider which message it answers. """
        received = self.account._om_whatsapp_receive('+32470123456', 'Can you deliver on Friday?', 'wamid.q1')
        channel = self._channel()
        reply = channel.with_user(self.user).message_post(body='Yes, Friday', message_type='comment',
                                                          parent_id=received.id)
        self.assertEqual(reply._om_whatsapp_quoted(), {'id': 'wamid.q1', 'from_me': False})
        reply.om_whatsapp_id = 'wamid.q2'
        again = channel.with_user(self.user).message_post(body='Morning', message_type='comment', parent_id=reply.id)
        self.assertEqual(again._om_whatsapp_quoted(), {'id': 'wamid.q2', 'from_me': True})
        plain = channel.with_user(self.user).message_post(body='Thanks', message_type='comment')
        self.assertFalse(plain._om_whatsapp_quoted())

    def test_reactions(self):
        """ One reaction per person, changed or taken back as in WhatsApp, on
        every copy of the message. """
        order = self.env['res.partner'].create({'name': 'S00012'})
        sent = self._post(order, 'Your order is ready', partner=self.alice)
        sent.om_whatsapp_id = 'wamid.1'
        sent._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        copies = self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.1')])
        self.assertEqual(len(copies), 2)

        def reactions():
            return copies.reaction_ids.mapped(lambda r: (r.partner_id, r.content))

        self.account._om_whatsapp_receive_reaction('+32470123456', 'wamid.1', '👍')
        self.assertEqual(reactions(), [(self.alice, '👍')] * 2)
        self.account._om_whatsapp_receive_reaction('+32470123456', 'wamid.1', '❤️')
        self.assertEqual(reactions(), [(self.alice, '❤️')] * 2)
        self.account.with_user(self.user)._om_whatsapp_receive_reaction('+32470123456', 'wamid.1', '🙏', from_me=True)
        self.assertEqual(len(copies.reaction_ids), 4)
        self.account._om_whatsapp_receive_reaction('+32470123456', 'wamid.1', '')
        self.assertEqual(reactions(), [(self.user.partner_id, '🙏')] * 2)
        self.assertFalse(self.account._om_whatsapp_receive_reaction('+32470123456', 'wamid.404', '👍'))

    def _sent_with_copies(self, whatsapp_id='wamid.2'):
        order = self.env['res.partner'].create({'name': 'S00013'})
        sent = self._post(order, 'Your order is ready', partner=self.alice)
        sent.om_whatsapp_id = whatsapp_id
        sent._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        copies = self.env['mail.message'].search([('om_whatsapp_id', '=', whatsapp_id)], order='id')
        self.assertEqual(len(copies), 2)
        return copies

    def test_reaction_of_a_user_goes_to_whatsapp(self):
        """ One reaction per person, as in WhatsApp: a new one replaces the
        one before, on every copy, and goes to the provider; taken back, an
        empty emoji goes. """
        copies = self._sent_with_copies()
        message = copies[-1].with_user(self.user)
        partner, guest = self.user.partner_id, self.env['mail.guest']
        with patch.object(OmWhatsappAccount, '_om_whatsapp_react_link', create=True, return_value=None) as react:
            message.sudo()._message_reaction('👍', 'add', partner, guest)
            self.assertEqual(copies.reaction_ids.mapped('content'), ['👍', '👍'])
            message.sudo()._message_reaction('❤️', 'add', partner, guest)
            self.assertEqual(copies.reaction_ids.mapped('content'), ['❤️', '❤️'])
            message.sudo()._message_reaction('❤️', 'remove', partner, guest)
            self.assertFalse(copies.reaction_ids)
        self.assertEqual([call.args[0] for call in react.call_args_list], ['+32470123456'] * 3)
        self.assertEqual([call.args[2:] for call in react.call_args_list], [('👍', True), ('❤️', True), ('', True)])
        self.assertEqual(react.call_args.args[1].om_whatsapp_id, 'wamid.2')

    def test_reaction_not_sent(self):
        """ Not by someone outside the account, nor on a message without its
        WhatsApp id; a provider that fails keeps the reaction in Odoo and
        tells the user. """
        copies = self._sent_with_copies()
        guest = self.env['mail.guest']
        with patch.object(OmWhatsappAccount, '_om_whatsapp_react_link', create=True) as react:
            copies[-1].sudo()._message_reaction('👍', 'add', self.other.partner_id, guest)
            no_id = self._post(self.env['res.partner'].create({'name': 'S00014'}), 'Hi', partner=self.alice)
            no_id.sudo()._message_reaction('👍', 'add', self.user.partner_id, guest)
        react.assert_not_called()
        self.assertEqual(len(copies[-1].reaction_ids), 1, "the copies are left alone")
        with patch.object(OmWhatsappAccount, '_om_whatsapp_react_link', create=True, side_effect=UserError('Not linked')), \
             patch.object(type(self.env.user), '_bus_send', autospec=True) as bus_send, \
             self.assertLogs('odoo.addons.om_whatsapp_base.models.om_whatsapp_account', level='WARNING'):
            copies[-1].with_user(self.user).sudo()._message_reaction('🙏', 'add', self.user.partner_id, guest)
        self.assertIn('🙏', copies[-1].reaction_ids.mapped('content'))
        notification = [c.args for c in bus_send.call_args_list if c.args[1] == 'simple_notification']
        self.assertEqual(notification[0][2]['message'], 'The reaction was not sent to WhatsApp: Not linked')

    def test_reply_goes_to_the_document(self):
        """ A reply goes to the document of the message it quotes, else to the
        one of the last message sent to that number within the window; and
        to the conversation, which shows that document. """
        order, invoice = self.env['res.partner'].create([{'name': 'S00012'}, {'name': 'INV/001'}])
        sent_order = self._post(order, partner=self.alice)
        sent_order.om_whatsapp_id = 'wamid.order'
        sent_invoice = self._post(invoice, partner=self.alice)
        for message in sent_order | sent_invoice:
            message._om_whatsapp_notifications()._om_whatsapp_set_status('sent')

        def replies(whatsapp_id):
            return self.env['mail.message'].search([('om_whatsapp_id', '=', whatsapp_id)]).mapped(lambda m: (m.model, m.res_id))

        channel = self._channel()
        self.account._om_whatsapp_receive('+32470123456', 'About the order', 'wamid.3', quoted_id='wamid.order')
        self.assertEqual(self.env['mail.message'].search([('om_whatsapp_id', '=', 'wamid.3'), ('model', '=', 'discuss.channel')]).parent_id.om_whatsapp_id, 'wamid.order')
        self.assertCountEqual(replies('wamid.3'), [('res.partner', order.id), ('discuss.channel', channel.id)])
        latest = self.account._om_whatsapp_receive('+32470123456', 'Thanks', 'wamid.4')
        self.assertCountEqual(replies('wamid.4'), [('res.partner', invoice.id), ('discuss.channel', channel.id)])
        self.assertEqual(latest.author_id, self.alice)

        (sent_order | sent_invoice).date = fields.Datetime.now() - timedelta(days=8)
        self.account._om_whatsapp_receive('+32470123456', 'Hello again', 'wamid.5')
        self.assertEqual(replies('wamid.5'), [('discuss.channel', channel.id)])

    def test_sent_from_the_phone(self):
        message = self.account.with_user(self.user)._om_whatsapp_receive(
            '+32470123456', 'Sent from my phone', 'wamid.6', from_me=True)
        self.assertEqual((message.model, message.res_id), ('discuss.channel', self._channel().id))
        self.assertEqual(message.author_id, self.user.partner_id)
        self.assertEqual(message.om_whatsapp_status, 'sent')
        self.assertEqual(message._om_whatsapp_notifications().res_partner_id, self.alice)
        self.account._om_whatsapp_update_status('wamid.6', 'read')
        self.assertEqual(message.om_whatsapp_status, 'read')

    def test_sent_message_goes_to_the_conversation(self):
        """ Once sent, a message of a document is in the conversation too,
        where its ticks follow the same updates. """
        order = self.env['res.partner'].create({'name': 'S00012'})
        message = self._post(order, 'Your order is ready', partner=self.alice)
        self.assertFalse(self._channel())
        message.om_whatsapp_id = 'wamid.7'
        message._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        channel = self._channel()
        copy = channel.message_ids.filtered(lambda m: m.om_whatsapp_id == 'wamid.7')
        self.assertEqual((copy.author_id, copy._om_whatsapp_text()), (message.author_id, 'Your order is ready'))
        self.assertEqual(copy.om_whatsapp_status, 'sent')
        self.account._om_whatsapp_update_status('wamid.7', 'read')
        self.assertEqual((message.om_whatsapp_status, copy.om_whatsapp_status), ('read', 'read'))
        message._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        self.assertEqual(len(channel.message_ids.filtered(lambda m: m.om_whatsapp_id == 'wamid.7')), 1)

    def test_answer_from_the_conversation(self):
        """ What a user writes in the conversation goes out on WhatsApp. """
        self.account._om_whatsapp_receive('+32470123456', 'Is it ready?', 'wamid.1')
        channel = self._channel().with_user(self.user)
        answer = channel.message_post(body='Yes, tomorrow', message_type='comment', subtype_xmlid='mail.mt_comment')
        self.assertEqual(answer.message_type, 'om_whatsapp')
        notification = answer._om_whatsapp_notifications()
        self.assertEqual((notification.om_whatsapp_number, notification.res_partner_id), ('+32470123456', self.alice))
        # Click to Chat opens the chat: sent
        self.assertEqual(answer.om_whatsapp_status, 'sent')
        self.assertEqual(len(channel.message_ids.filtered(lambda m: m._om_whatsapp_text() == 'Yes, tomorrow')), 1)
        with self.assertRaises(UserError):
            channel.with_user(self.other).message_post(body='Hi', message_type='comment')

    def test_users_send_only_from_their_accounts(self):
        with self.assertRaises(AccessError):
            self.account.with_user(self.other).check_access('read')
        with self.assertRaises(UserError):
            self.account.with_user(self.other)._om_whatsapp_check_user()

    def test_template_action_menu(self):
        self.template.action_create_sidebar_action()
        action = self.template.sidebar_action_id
        self.assertEqual(action.binding_model_id.model, 'res.partner')
        self.template.unlink()
        self.assertFalse(action.exists())


    def test_conversation_made_by_account_only(self):
        """ Discuss lets a user make chats: not the conversation of a number,
        which would bring them its messages. """
        stranger = new_test_user(self.env, 'om_whatsapp_stranger', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['discuss.channel'].with_user(stranger).create({
                'name': 'Alice', 'channel_type': 'om_whatsapp',
                'om_whatsapp_account_id': self.account.id, 'om_whatsapp_number': '+32470123456',
            })
        channel = self.account._om_whatsapp_get_channel('+32470123456', self.alice)
        with self.assertRaises(AccessError):
            channel.with_user(self.user).write({'om_whatsapp_res_model': 'res.users', 'om_whatsapp_res_id': 2})
        with self.assertRaises(AccessError):
            channel.with_user(self.user).write({'channel_type': 'group'})
        channel.with_user(self.user).write({'name': 'Alice (shop)'})

    def test_whatsapp_message_made_by_account_only(self):
        """ No faked message of a customer, nor a taken WhatsApp id: replies
        to it would go to the document of who took it. """
        # Odoo 18 asks an email of who posts, before anything else
        (self.user | self.other).email = 'om_whatsapp_user@example.com'
        self.account._om_whatsapp_receive('+32470123456', 'Hi', whatsapp_id='wamid.real')
        partner = self.bob.with_user(self.other)
        with self.assertRaises(AccessError):
            partner.message_post(body='I accept', message_type='om_whatsapp', author_id=self.alice.id,
                                 email_from='alice@example.com', om_whatsapp_account_id=self.account.id)
        with self.assertRaises(AccessError):
            self.bob.with_user(self.user).message_post(body='I accept', message_type='om_whatsapp',
                                                       om_whatsapp_account_id=self.account.id, om_whatsapp_id='wamid.real')
        with self.assertRaises(AccessError):
            partner.message_post(body='Hi', message_type='om_whatsapp')
        sent = self.bob.with_user(self.user).message_post(body='Hello', message_type='om_whatsapp',
                                                          om_whatsapp_account_id=self.account.id)
        with self.assertRaises(AccessError):
            sent.with_user(self.other).write({'om_whatsapp_id': 'wamid.mine'})

@tagged('post_install', '-at_install')
class TestOmWhatsappAutomation(TransactionCase):
    """ The Send WhatsApp server action, as an automation rule runs it. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_whatsapp_auto',
                                 groups='base.group_user,base.group_partner_manager,om_whatsapp_base.group_om_whatsapp_user')
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Sales', 'provider': 'link', 'user_ids': [Command.set(cls.user.ids)],
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice', 'phone': '+32470123456'})
        cls.bob = cls.env['res.partner'].create({'name': 'Bob', 'phone': '+32470654321'})
        cls.template = cls.env['om.whatsapp.template'].create({
            'name': 'Welcome',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'body': 'Welcome {{ object.name }}',
        })
        cls.action = cls.env['ir.actions.server'].create({
            'name': 'Welcome on WhatsApp',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'state': 'om_whatsapp',
            'om_whatsapp_template_id': cls.template.id,
            'om_whatsapp_account_id': cls.account.id,
        })

    def _run(self, partners):
        self.action.with_user(self.user).with_context(
            active_model='res.partner', active_ids=partners.ids, active_id=partners[:1].id).run()

    def _messages(self, partners):
        return self.env['mail.message'].search(
            [('model', '=', 'res.partner'), ('res_id', 'in', partners.ids), ('message_type', '=', 'om_whatsapp')])

    def test_action_form(self):
        self.assertIn(self.env['ir.model']._get('sale.order') or self.env['ir.model']._get('res.partner'),
                      self.action.available_model_ids)
        self.assertNotIn(self.env['ir.model']._get('om.whatsapp.composer'), self.action.available_model_ids)
        self.action.model_id = self.env['ir.model']._get('phone.blacklist')
        self.assertFalse(self.action.om_whatsapp_template_id)

    def test_a_provider_sending_from_the_server_sends_each_record(self):
        self.env['phone.blacklist'].sudo().create({'number': '+32470654321'})
        with patch.object(OmWhatsappAccount, '_compute_capabilities', _from_server), \
             patch.object(OmWhatsappAccount, '_om_whatsapp_send_link', autospec=True,
                          side_effect=lambda account, notifications: notifications._om_whatsapp_set_status('sent')) as send:
            self._run(self.alice | self.bob)
        self.assertEqual(send.call_args.args[1].res_partner_id, self.alice)
        alice, bob = self._messages(self.alice), self._messages(self.bob)
        self.assertEqual((alice._om_whatsapp_text(), alice.om_whatsapp_status), ('Welcome Alice', 'sent'))
        self.assertEqual(alice.author_id, self.user.partner_id)
        self.assertEqual(bob.om_whatsapp_status, 'cancel')

    def test_click_to_chat_cannot_send_by_itself(self):
        self._run(self.alice)
        message = self._messages(self.alice)
        self.assertEqual(message.om_whatsapp_status, 'failed')
        self.assertIn('cannot send by itself', message._om_whatsapp_notifications().failure_reason)

    def test_sending_never_stops_the_flow(self):
        """ No account, or a provider that breaks: the record is saved, the
        problem logged. """
        self.action.om_whatsapp_account_id = False
        self.env['om.whatsapp.account'].search([]).user_ids = [Command.unlink(self.user.id)]
        with self.assertLogs('odoo.addons.om_whatsapp_base.models.mail_thread', level='WARNING'):
            self._run(self.alice)
        self.assertFalse(self._messages(self.alice))
        self.action.om_whatsapp_account_id = self.account
        with patch.object(OmWhatsappAccount, '_om_whatsapp_send_automated', side_effect=RuntimeError('down')), \
             self.assertLogs('odoo.addons.om_whatsapp_base.models.mail_thread', level='ERROR'):
            self._run(self.alice)
        self.assertFalse(self._messages(self.alice))
