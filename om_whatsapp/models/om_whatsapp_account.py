import logging
import mimetypes
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import db_list

from odoo.addons.om_whatsapp.models.om_whatsapp_template import META_STATES, META_VARIABLE
from odoo.addons.om_whatsapp.tools import MetaApi, MetaApiError

_logger = logging.getLogger(__name__)

# what Meta says of a message sent, as the status of Odoo
META_STATUS = {'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed'}
# kinds of messages received with a file
MEDIA_RECEIVED = {'image', 'document', 'audio', 'video', 'sticker'}

# what Meta sends as such, with its limits (bytes); the rest goes as a document
MEDIA_KINDS = {
    'image': ({'image/jpeg', 'image/png'}, 5 * 1024 * 1024),
    'video': ({'video/mp4', 'video/3gpp'}, 16 * 1024 * 1024),
    'audio': ({'audio/aac', 'audio/amr', 'audio/mpeg', 'audio/mp4', 'audio/ogg'}, 16 * 1024 * 1024),
}
CAPTIONED = {'image', 'video', 'document'}


def media_kind(attachment):
    for kind, (mimetypes, size) in MEDIA_KINDS.items():
        if attachment.mimetype in mimetypes and attachment.file_size <= size:
            return kind
    return 'document'


# what the webhook of the app brings
WEBHOOK_FIELDS = ['messages', 'message_template_status_update', 'phone_number_quality_update', 'account_update']
WEBHOOK_PATH = '/om_whatsapp/webhook'


class OmWhatsappAccount(models.Model):
    """ Meta: the WhatsApp Cloud API, from the app of the company in Meta for
    Developers. The setup assistant needs its App ID, App Secret and access
    token, and does the rest: the number, its registration, the webhook. """
    _inherit = 'om.whatsapp.account'

    provider = fields.Selection(selection_add=[('meta', 'Meta (Cloud API)')], ondelete={'meta': 'set default'})
    meta_app_id = fields.Char('App ID', groups='om_whatsapp_base.group_om_whatsapp_manager', copy=False)
    meta_app_secret = fields.Char('App Secret', groups='om_whatsapp_base.group_om_whatsapp_manager', copy=False)
    meta_access_token = fields.Char('Access Token', groups='om_whatsapp_base.group_om_whatsapp_manager', copy=False)
    meta_waba_id = fields.Char('WhatsApp Business Account ID', readonly=True, copy=False)
    meta_waba_name = fields.Char('Business Account', readonly=True, copy=False)
    meta_phone_number_id = fields.Char('Phone Number ID', readonly=True, copy=False, index='btree_not_null')
    meta_verified_name = fields.Char('WhatsApp Name', readonly=True, copy=False,
                                     help="The name of the business shown in WhatsApp, approved by Meta.")
    meta_quality_rating = fields.Char('Quality Rating', readonly=True, copy=False)
    meta_messaging_limit = fields.Char('Messaging Limit', readonly=True, copy=False)
    meta_pin = fields.Char('Two-step Verification PIN', groups='om_whatsapp_base.group_om_whatsapp_manager', copy=False,
                           help="Set on the number when Odoo registers it. Keep it: Meta asks for it to register the "
                                "number elsewhere.")
    meta_verify_token = fields.Char(
        'Webhook Verify Token', groups='om_whatsapp_base.group_om_whatsapp_manager', copy=False,
        default=lambda self: secrets.token_urlsafe(24))
    meta_webhook_url = fields.Char('Webhook Callback URL', compute='_compute_meta_webhook_url')
    meta_state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connected', 'Connected'),
        ('error', 'Needs Attention'),
    ], string='Connection', default='draft', readonly=True, copy=False)
    meta_status_message = fields.Text('Connection Status', readonly=True, copy=False)
    meta_checked_on = fields.Datetime('Last Checked', readonly=True, copy=False)
    meta_token_expires = fields.Datetime(
        'Token Expires', readonly=True, copy=False,
        help="A temporary token of Meta works 24 hours: make the connection permanent before.")

    _meta_phone_number_unique = models.Constraint(
        'unique (meta_phone_number_id)', 'A Meta number is the number of one account only.')

    @api.depends('provider')
    def _compute_capabilities(self):
        super()._compute_capabilities()
        for account in self.filtered(lambda a: a.provider == 'meta'):
            account.can_send_files = True
            account.can_send_batch = True
            account.can_send_unattended = True

    def _compute_meta_webhook_url(self):
        """ The address of this Odoo, in https: the one Meta accepts. A
        tunnel or a proxy in front of Odoo gives https, while Odoo may know
        itself in http. """
        for account in self:
            url = urlparse(account.get_base_url().rstrip('/') + WEBHOOK_PATH)
            if url.scheme == 'http' and not account._meta_local_host(url.hostname):
                url = url._replace(scheme='https')
            account.meta_webhook_url = url.geturl()

    @staticmethod
    def _meta_local_host(host):
        host = host or ''
        return host in ('localhost', '127.0.0.1') or host.endswith('.local') or host.startswith(('192.168.', '10.'))

    def _meta_webhook_reachable(self):
        """ Meta calls an https address of the internet only. """
        self.ensure_one()
        url = urlparse(self.meta_webhook_url or '')
        return url.scheme == 'https' and not self._meta_local_host(url.hostname)

    def _meta_api(self):
        self.ensure_one()
        account = self.sudo()
        return MetaApi(self.env, access_token=account.meta_access_token, app_id=account.meta_app_id,
                       app_secret=account.meta_app_secret)

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------

    def _meta_check_manager(self):
        """ The buttons of Meta are hidden to users, not closed: what they
        change is checked here. """
        if not self.env.user.has_group('om_whatsapp_base.group_om_whatsapp_manager'):
            raise AccessError(_("Only WhatsApp managers manage the connection to Meta."))
        self.check_access('write')

    def action_meta_setup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Connect to Meta"),
            'res_model': 'om.whatsapp.meta.setup',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_account_id': self.id, 'dialog_size': 'extra-large'},
        }

    def action_meta_permanent_token(self):
        """ The assistant for the token of a system user, which never
        expires. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Make the Connection Permanent"),
            'res_model': 'om.whatsapp.meta.setup',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_account_id': self.id, 'default_step': 'permanent'},
        }

    def action_meta_disconnect(self):
        """ Free the number, to connect another one: the app stays, for
        Connect to Meta. """
        self.ensure_one()
        self._meta_check_manager()
        self.sudo().write({
            'meta_phone_number_id': False,
            'meta_state': 'draft',
            'meta_status_message': False,
            'meta_quality_rating': False,
            'meta_messaging_limit': False,
        })
        return True

    def action_meta_check(self):
        """ Check the connection again: the token, the number, the webhook. """
        self.ensure_one()
        self._meta_check_manager()
        problems = self._meta_check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning' if problems else 'success',
                'message': '\n'.join(problems) if problems else _("%(account)s is connected to Meta.", account=self.name),
                'sticky': bool(problems),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _meta_check(self):
        """ Refresh what Meta says of the number; the problems found. """
        self.ensure_one()
        account = self.sudo()
        problems = []
        api = self._meta_api()
        try:
            token = api.debug_token()
            expires = token.get('expires_at') or 0
            account.meta_token_expires = datetime.fromtimestamp(expires) if expires else False
            if not token.get('is_valid'):
                problems.append(_("The access token is not valid any more: click Make it Permanent, or connect again "
                                  "with a new temporary token."))
            if account.meta_phone_number_id:
                number = api.get_phone_number(account.meta_phone_number_id)
                account._meta_write_number(number)
            else:
                problems.append(_("No number is chosen: connect again."))
            if self._meta_webhook_reachable() and not self._meta_database_reachable():
                problems.append(self._meta_database_message())
            elif self._meta_webhook_reachable():
                subscriptions = api.get_webhook()
                webhook = next((s for s in subscriptions if s.get('object') == 'whatsapp_business_account'), {})
                if webhook.get('callback_url') != self.meta_webhook_url:
                    problems.append(_("The webhook of the app is not this Odoo: connect again."))
            else:
                problems.append(self._meta_unreachable_message())
        except MetaApiError as error:
            problems.append(_("Meta says: %(error)s", error=error))
        account.write({
            'meta_state': 'error' if problems else 'connected',
            'meta_status_message': '\n'.join(problems) or False,
            'meta_checked_on': fields.Datetime.now(),
        })
        return problems

    def _meta_database_reachable(self):
        """ Meta calls without a session: Odoo finds the database alone, the
        only one of the server, or the one its dbfilter keeps. """
        self.ensure_one()
        return db_list(force=True, host=urlparse(self.meta_webhook_url).hostname) == [self.env.cr.dbname]

    def _meta_database_message(self):
        return _("Meta calls %(url)s without saying which database: this Odoo server has several, and Meta gets a 404. "
                 "Keep this one for its address: in the configuration of Odoo, set dbfilter = ^%(db)s$ (or start it with "
                 "--db-filter=^%(db)s$), restart Odoo, then click Set Webhook.",
                 url=self.meta_webhook_url, db=self.env.cr.dbname)

    def _meta_unreachable_message(self):
        return _("Meta cannot reach %(url)s: the webhook needs this Odoo on a public https address. For a local Odoo, "
                 "run a tunnel (cloudflared or ngrok), set its address as the system parameter web.base.url, with "
                 "web.base.url.freeze set to True so that Odoo keeps it, then click Set Webhook. Until then, no message "
                 "nor status comes in.", url=self.meta_webhook_url)

    def action_meta_set_webhook(self):
        """ Have Meta send the messages of WhatsApp to this Odoo: again, once
        it is on a public address. """
        self.ensure_one()
        self._meta_check_manager()
        account = self.sudo()
        try:
            if not self._meta_webhook_reachable():
                raise UserError(self._meta_unreachable_message())
            if not self._meta_database_reachable():
                raise UserError(self._meta_database_message())
            api = self._meta_api()
            api.subscribe_app(account.meta_waba_id)
            api.set_webhook(self.meta_webhook_url, account.meta_verify_token, WEBHOOK_FIELDS)
        except MetaApiError as error:
            raise UserError(_("Meta says: %(error)s", error=error)) from error
        self._meta_check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Meta sends the messages of WhatsApp to %(url)s.", url=self.meta_webhook_url),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_meta_test_message(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send a Test Message"),
            'res_model': 'om.whatsapp.meta.setup',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_account_id': self.id, 'default_step': 'test'},
        }

    def _meta_explain(self, error):
        """ The words of Meta, with what to do for the errors met while trying. """
        hints = {
            131030: _("While you use the test number of Meta, it sends only to the numbers of its list. In your app: "
                      "WhatsApp › API Setup, open the To list, Manage phone number list, Add phone number; Meta sends a "
                      "code to that number on WhatsApp: enter it and Verify. Then send again, to exactly that number. The "
                      "Send Test Message button of the account shows these steps."),
            131047: _("The contact has not written in the last 24 hours: send an approved template."),
            190: _("The token expired: click Make it Permanent, or connect again with a new token."),
        }
        hint = hints.get(error.code)
        return f"{error} {hint}" if hint else str(error)

    def _meta_take_number(self, phone_number_id, display_number):
        """ A number is the number of one account. An archived account
        gives it up; an active one keeps it, and the user is told which. """
        self.ensure_one()
        other = self.with_context(active_test=False).sudo().search(
            [('meta_phone_number_id', '=', phone_number_id), ('id', '!=', self.id)], limit=1)
        if not other:
            return
        if other.active:
            raise UserError(_("%(number)s is the number of the account %(account)s: connect again from that account, or "
                              "archive it first.", number=display_number, account=other.name))
        other.write({'meta_phone_number_id': False, 'meta_state': 'draft', 'meta_status_message': False})

    def _meta_write_number(self, number):
        self.ensure_one()
        self.sudo().write({
            'meta_phone_number_id': number.get('id'),
            'meta_verified_name': number.get('verified_name'),
            'meta_quality_rating': number.get('quality_rating'),
            'meta_messaging_limit': number.get('messaging_limit_tier'),
            'phone': number.get('display_phone_number') or self.phone,
        })

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _om_whatsapp_send_meta(self, notifications):
        """ One message a user sends (composer, Discuss, send again) goes at
        once; several wait in the queue of the scheduled action, so that the
        user never waits for Meta. """
        self.ensure_one()
        if len(notifications) > 1:
            return self._meta_queue(notifications)
        self._meta_send(notifications)
        return None

    def _om_whatsapp_send_automated(self, notifications):
        """ An automation rule queues: the confirmation of an order never
        waits for Meta. """
        self.ensure_one()
        if self.provider != 'meta':
            return super()._om_whatsapp_send_automated(notifications)
        return self._meta_queue(notifications)

    def _meta_queue(self, notifications):
        self.env.ref('om_whatsapp.ir_cron_meta_send_queue')._trigger()
        return None

    @api.model
    def _cron_meta_send_queue(self, limit=200):
        """ Send the queued messages of the Meta accounts, one after the
        other, saved one by one. """
        Notification = self.env['mail.notification'].sudo()
        notifications = Notification.search([
            ('notification_type', '=', 'om_whatsapp'),
            ('notification_status', '=', 'ready'),
            ('mail_message_id.om_whatsapp_account_id.provider', '=', 'meta'),
        ], order='id', limit=limit)
        for account in notifications.mail_message_id.om_whatsapp_account_id:
            for notification in notifications.filtered(lambda n: n.mail_message_id.om_whatsapp_account_id == account):
                account._meta_send(notification)
                if self.env.context.get('cron_id'):
                    self.env['ir.cron']._commit_progress(1, remaining=0)
        if len(notifications) == limit:
            self.env.ref('om_whatsapp.ir_cron_meta_send_queue')._trigger()

    def _meta_send(self, notifications):
        """ Send from the server, one message after the other: Meta answers
        with the id of the message, the webhook tells the rest. """
        self.ensure_one()
        if self.meta_state == 'draft' or not self.meta_phone_number_id:
            notifications._om_whatsapp_set_status('failed', _("%(account)s is not connected to Meta.", account=self.name))
            return
        api = self._meta_api()
        for notification in notifications:
            try:
                whatsapp_id = self._meta_send_notification(api, notification)
            except MetaApiError as error:
                notification._om_whatsapp_set_status('failed', self._meta_explain(error))
                continue
            except UserError as error:
                notification._om_whatsapp_set_status('failed', str(error))
                continue
            notification.mail_message_id.sudo().om_whatsapp_id = whatsapp_id
            notification._om_whatsapp_set_status('sent')

    def _meta_send_notification(self, api, notification):
        """ An approved template of Meta, with the PDF as its header; else the
        text, or the files with the text as the caption of the first, within
        the 24 hours after the last message of the number. The id of the
        first message, which a reply quotes. """
        self.ensure_one()
        message = notification.mail_message_id.sudo()
        to = ''.join(char for char in notification.om_whatsapp_number or '' if char.isdigit())
        template = message.om_whatsapp_template_id
        record = self.env[message.model].browse(message.res_id).exists() \
            if message.model and message.model in self.env and message.model != 'discuss.channel' else None
        attachments = message.attachment_ids
        payloads = []
        if template and template._meta_ready(self) and record:
            components = []
            if template.report_id and attachments:
                header, attachments = attachments[0], attachments[1:]
                media_id = api.upload_media(self.meta_phone_number_id, header.name, header.raw, header.mimetype)
                components.append({'type': 'header', 'parameters': [
                    {'type': 'document', 'document': {'id': media_id, 'filename': header.name}}]})
            if parameters := template._meta_parameters(record):
                components.append({'type': 'body', 'parameters': [{'type': 'text', 'text': value} for value in parameters]})
            payloads.append({'to': to, 'type': 'template', 'template': {
                'name': template.meta_name, 'language': {'code': template.meta_language}, 'components': components}})
            text = ''
        else:
            self._meta_check_window(notification.om_whatsapp_number)
            text = message._om_whatsapp_text()
        for attachment in attachments:
            kind = media_kind(attachment)
            media_id = api.upload_media(self.meta_phone_number_id, attachment.name, attachment.raw, attachment.mimetype)
            media = {'id': media_id}
            if kind == 'document':
                media['filename'] = attachment.name
            if text and not payloads and kind in CAPTIONED:
                media['caption'] = text
                text = ''
            payloads.append({'to': to, 'type': kind, kind: media})
        if text:
            payloads.insert(0, {'to': to, 'type': 'text', 'text': {'body': text, 'preview_url': True}})
        if not payloads:
            raise UserError(_("The message is empty."))
        if quoted := message._om_whatsapp_quoted():
            # a reply in Discuss: the first message quotes the one it answers
            payloads[0]['context'] = {'message_id': quoted['id']}
        ids = [api.send_message(self.meta_phone_number_id, payload) for payload in payloads]
        return ids[0]

    def _om_whatsapp_receipt_meta(self, number, whatsapp_ids, kind):
        """ Meta takes a read receipt for the last message, and marks the ones
        before read too; it has no played receipt: a played voice message is
        read. """
        self.ensure_one()
        if self.meta_state == 'draft' or not self.meta_phone_number_id:
            raise UserError(_("%(account)s is not connected to Meta.", account=self.name))
        self._meta_api().mark_read(self.meta_phone_number_id, whatsapp_ids[-1])
        return None

    def _om_whatsapp_react_meta(self, number, message, emoji, from_me):
        """ A reaction goes at once, from the server: an empty emoji takes it back. """
        self.ensure_one()
        if self.meta_state == 'draft' or not self.meta_phone_number_id:
            raise UserError(_("%(account)s is not connected to Meta.", account=self.name))
        try:
            self._meta_api().send_message(self.meta_phone_number_id, {
                'to': ''.join(char for char in number if char.isdigit()),
                'recipient_type': 'individual',
                'type': 'reaction',
                'reaction': {'message_id': message.om_whatsapp_id, 'emoji': emoji},
            })
        except MetaApiError as error:
            raise UserError(self._meta_explain(error)) from error
        return None

    # ------------------------------------------------------------
    # THE 24 HOURS
    # ------------------------------------------------------------

    def _om_whatsapp_free_text_until(self, channel):
        """ Meta takes free text within 24 hours of the last message of the
        number; before any, never. """
        if self.provider != 'meta':
            return super()._om_whatsapp_free_text_until(channel)
        last = channel.om_whatsapp_last_incoming
        return last + timedelta(hours=24) if last else datetime(2000, 1, 1)

    def _meta_check_window(self, number):
        number = self._om_whatsapp_clean_number(number)
        channel = self.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'om_whatsapp'), ('om_whatsapp_account_id', '=', self.id),
            ('om_whatsapp_number', '=', number),
        ], limit=1)
        if not channel:
            channel = self.env['discuss.channel'].new({'name': number, 'om_whatsapp_number': number})
        self._om_whatsapp_check_free_text(channel)

    def _meta_send_template(self, number, name, language='en_US', components=None):
        """ Send a template of Meta by its name: the one way to write first to
        a number, outside the 24 hours after its last message. """
        self.ensure_one()
        template = {'name': name, 'language': {'code': language}}
        if components:
            template['components'] = components
        return self._meta_api().send_message(self.meta_phone_number_id, {
            'to': ''.join(char for char in number if char.isdigit()),
            'type': 'template',
            'template': template,
        })

    # ------------------------------------------------------------
    # RECEIVING: THE WEBHOOK
    # ------------------------------------------------------------

    def _meta_process_webhook(self, field, value):
        """ One change posted by Meta to the webhook. """
        self.ensure_one()
        if field == 'messages':
            names = {contact.get('wa_id'): (contact.get('profile') or {}).get('name') for contact in value.get('contacts') or []}
            for message in value.get('messages') or []:
                self._meta_receive_message(message, names.get(message.get('from')))
            for status in value.get('statuses') or []:
                self._meta_receive_status(status)
        elif field == 'message_template_status_update':
            template = self.env['om.whatsapp.template'].with_context(active_test=False).search(
                [('meta_template_id', '=', str(value.get('message_template_id')))], limit=1)
            if template and value.get('event') in dict(META_STATES):
                template.with_context(om_whatsapp_meta_sync=True).write({
                    'meta_status': value['event'],
                    'meta_reason': value.get('reason') if value.get('reason') not in (None, 'NONE') else False,
                })
            elif not template:
                # a template made in Meta: it comes to Odoo with the others
                self._meta_sync_templates_quietly()
        elif field == 'phone_number_quality_update':
            self.sudo().write({
                'meta_quality_rating': value.get('event') or self.meta_quality_rating,
                'meta_messaging_limit': value.get('current_limit') or self.meta_messaging_limit,
            })
        else:
            _logger.info("WhatsApp webhook %s of %s: %s", field, self.name, value)

    def _meta_receive_status(self, status):
        state = META_STATUS.get(status.get('status'))
        if not state or not status.get('id'):
            return
        reasons = []
        for error in status.get('errors') or []:
            reasons.append((error.get('error_data') or {}).get('details') or error.get('message') or error.get('title') or '')
        self._om_whatsapp_update_status(status['id'], state, '; '.join(filter(None, reasons)) or False)

    def _meta_receive_message(self, message, profile_name=None):
        kind = message.get('type')
        number = f"+{message.get('from')}"
        if kind == 'reaction':
            reaction = message.get('reaction') or {}
            self._om_whatsapp_receive_reaction(number, reaction.get('message_id'), reaction.get('emoji') or '')
            return
        body, attachments, voice = '', [], False
        if kind == 'text':
            body = (message.get('text') or {}).get('body') or ''
        elif kind == 'button':
            body = (message.get('button') or {}).get('text') or ''
        elif kind == 'interactive':
            interactive = message.get('interactive') or {}
            body = (interactive.get('button_reply') or interactive.get('list_reply') or {}).get('title') or ''
        elif kind == 'location':
            location = message.get('location') or {}
            place = ' '.join(filter(None, [location.get('name'), location.get('address')]))
            body = _("[Location] %(place)s https://maps.google.com/?q=%(lat)s,%(long)s",
                     place=place, lat=location.get('latitude'), long=location.get('longitude'))
        elif kind in MEDIA_RECEIVED:
            media = message.get(kind) or {}
            body = media.get('caption') or ''
            voice = kind == 'audio' and bool(media.get('voice'))
            try:
                content, mimetype = self._meta_api().download_media(media.get('id'))
                extension = mimetypes.guess_extension((mimetype or '').split(';')[0]) or ''
                name = media.get('filename') or f"{'voice-message' if voice else kind}-{message.get('id', '')[-8:]}{extension}"
                attachments.append((name, content))
            except MetaApiError as error:
                body = '\n'.join(filter(None, [body, _("(The file could not be downloaded from Meta: %(error)s)", error=error)]))
        else:
            body = f"[{kind}]"
        self._om_whatsapp_receive(
            number, body,
            whatsapp_id=message.get('id'),
            attachments=attachments,
            quoted_id=(message.get('context') or {}).get('id') or False,
            profile_name=profile_name or False,
            voice=voice and bool(attachments),
        )

    # ------------------------------------------------------------
    # TEMPLATES
    # ------------------------------------------------------------

    def action_meta_sync_templates(self):
        self.ensure_one()
        self._meta_check_manager()
        count = self._meta_sync_templates()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Templates synchronized with Meta; %(count)s new one(s), archived until their fields are set.",
                             count=count),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _cron_meta_sync_templates(self):
        """ Once a day, what the webhook may have missed: the templates made
        in Meta, and the status of the others. """
        for account in self.search([('provider', '=', 'meta'), ('meta_state', '=', 'connected')]):
            account._meta_sync_templates_quietly()
            if self.env.context.get('cron_id'):
                self.env.cr.commit()

    def _meta_sync_templates_quietly(self):
        """ Sync without stopping the webhook or the cron: Meta not answering
        is only logged. """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                return self._meta_sync_templates()
        except UserError as error:
            _logger.info("WhatsApp templates of %s not synced: %s", self.name, error)
            return 0

    def _meta_sync_templates(self):
        """ The status of the templates of Meta, and the ones made there:
        those come archived, as templates of contacts, until their fields
        are set. The number of new ones. """
        self.ensure_one()
        Template = self.env['om.whatsapp.template'].with_context(active_test=False, om_whatsapp_meta_sync=True)
        try:
            remote = self._meta_api().get_templates(self.meta_waba_id)
        except MetaApiError as error:
            raise UserError(_("Meta says: %(error)s", error=error)) from error
        known = {t.meta_template_id: t for t in Template.search([('meta_template_id', 'in', [r.get('id') for r in remote])])}
        created = 0
        for data in remote:
            status = data.get('status') if data.get('status') in dict(META_STATES) else 'PENDING'
            values = {'meta_status': status, 'meta_reason': data.get('rejected_reason') not in (None, 'NONE')
                      and data.get('rejected_reason') or False, 'meta_category': data.get('category')}
            if template := known.get(data.get('id')):
                template.write(values)
                continue
            components = {c.get('type'): c for c in data.get('components') or []}
            text = (components.get('BODY') or {}).get('text') or ''
            Template.create({
                **values,
                'name': data.get('name'),
                'active': False,
                'model_id': self.env['ir.model']._get_id('res.partner'),
                'account_id': self.id,
                'meta_name': data.get('name'),
                'meta_language': data.get('language'),
                'meta_template_id': data.get('id'),
                'meta_waba_id': self.meta_waba_id,
                'meta_footer': (components.get('FOOTER') or {}).get('text'),
                # {{1}} until a field is set in its place, e.g. {{ object.partner_id.name }}
                'body': META_VARIABLE.sub(lambda match: "{{ '%s' }}" % match.group(1), text),
            })
            created += 1
        return created
