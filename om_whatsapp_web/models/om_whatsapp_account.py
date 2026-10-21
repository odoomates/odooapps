import base64
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# the last connection of an account is recorded at most this often
SEEN_EVERY = timedelta(seconds=60)
# a profile picture the browser could not read is downloaded by Odoo, from WhatsApp only
PICTURE_MAX_SIZE = 2 * 1024 * 1024
PICTURE_TIMEOUT = 10
# the clocks of the phone and of Odoo may differ a little
START_MARGIN = timedelta(seconds=60)


class OmWhatsappAccount(models.Model):
    """ WhatsApp Web: the browser sends. The composer hands the queued message
    to the ``om_whatsapp_web_send`` client action, which passes it to the
    browser extension, and the extension to the WhatsApp Web tab. The
    extension also reads the messages of WhatsApp Web, which the Odoo page
    hands back here. """
    _inherit = 'om.whatsapp.account'

    provider = fields.Selection(selection_add=[('web', 'WhatsApp Web')], ondelete={'web': 'set default'}, default='web')
    om_whatsapp_web_seen = fields.Datetime(
        'Last Connected', readonly=True, copy=False,
        help="The last time WhatsApp Web was open and linked to this number in the browser of a user, with the "
             "extension.")
    om_whatsapp_web_seen_user_id = fields.Many2one('res.users', 'Last Connected By', readonly=True, copy=False)
    om_whatsapp_web_since = fields.Datetime(
        'Messages Since', readonly=True, copy=False,
        help="WhatsApp Web first connected to this account: the messages from then on come to Odoo, the chats before "
             "stay in WhatsApp. The browser extension keeps the messages it read for any Odoo, a new database too.")

    @api.depends('provider')
    def _compute_capabilities(self):
        super()._compute_capabilities()
        for account in self.filtered(lambda a: a.provider == 'web'):
            account.can_send_files = True

    def _om_whatsapp_send_automated(self, notifications):
        """ WhatsApp Web sends what a user does: one message, triggered from
        their browser (an order they confirm), goes through it as from
        Discuss. Several at once, or without a user, would be the bulk
        sending WhatsApp bans numbers for: they wait for a user to send them
        again from the chatter. """
        self.ensure_one()
        if self.provider != 'web':
            return super()._om_whatsapp_send_automated(notifications)
        if len(notifications) == 1 and self._om_whatsapp_user_at_screen():
            action = self._om_whatsapp_send(notifications)
            self.env.user._bus_send('om_whatsapp/action', {'action': action})
            return None
        notifications._om_whatsapp_set_status('failed', _(
            "WhatsApp Web sends the messages of a user one by one, not by itself: send it again from the chatter."))
        return None

    def _om_whatsapp_send_web(self, notifications):
        return {
            'type': 'ir.actions.client',
            'tag': 'om_whatsapp_web_send',
            'params': {'notification_ids': notifications.ids},
        }

    def _om_whatsapp_receipt_web(self, number, whatsapp_ids, kind):
        """ The browser of the user marks them read or played, in WhatsApp Web. """
        return {
            'type': 'ir.actions.client',
            'tag': 'om_whatsapp_web_receipt',
            'params': {'phone': ''.join(char for char in number if char.isdigit()), 'ids': whatsapp_ids, 'kind': kind},
        }

    def _om_whatsapp_react_web(self, number, message, emoji, from_me):
        """ The browser of the user reacts, in WhatsApp Web. """
        return {
            'type': 'ir.actions.client',
            'tag': 'om_whatsapp_web_react',
            'params': {
                'phone': ''.join(char for char in number if char.isdigit()),
                'whatsapp_id': message.om_whatsapp_id,
                'emoji': emoji,
            },
        }

    # ------------------------------------------------------------
    # RECEIVING, from the extension through the Odoo page
    # ------------------------------------------------------------

    @api.model
    def _om_whatsapp_web_account(self, me):
        """ The WhatsApp Web account of the current user for the number ``me``
        linked in their browser. An account without a number takes any, when
        it is the only one of the user; a WhatsApp linked to another number is
        never read into an account. """
        accounts = self.search([
            ('provider', '=', 'web'), ('user_ids', 'in', self.env.uid), ('company_id', 'in', self.env.companies.ids),
        ])
        digits = lambda value: ''.join(char for char in value or '' if char.isdigit())  # noqa: E731
        matching = accounts.filtered(lambda a: me and digits(a.phone) == digits(me))
        if matching:
            return matching[:1]
        if len(accounts) == 1 and not accounts.phone:
            return accounts
        return self.browse()

    def _om_whatsapp_web_start(self):
        """ The messages come from the first connection on; an account
        connected before this was recorded starts from its last one. """
        self.ensure_one()
        if not self.om_whatsapp_web_since:
            # sudo: a user of the account may not write it
            self.sudo().om_whatsapp_web_since = self.om_whatsapp_web_seen or fields.Datetime.now()

    def _om_whatsapp_web_is_old(self, item):
        """ Whether a message read in WhatsApp Web is from before the account
        started: the extension still has it from another Odoo. """
        self.ensure_one()
        sent_at = item.get('t')
        if item.get('kind') != 'message' or not sent_at or not isinstance(sent_at, (int, float)):
            return False
        self._om_whatsapp_web_start()
        sent_at = datetime.fromtimestamp(sent_at, timezone.utc).replace(tzinfo=None)
        return sent_at < self.om_whatsapp_web_since - START_MARGIN

    @api.model
    def om_whatsapp_web_status(self, me=False):
        """ The pages of a user tell the status of WhatsApp Web in their
        browser: ``me`` is the number linked there, when it is open. The
        account of that number records the connection, at most once a minute.

        :return: {'has_account': whether the user has a WhatsApp Web account,
                  'account': {id, name, phone} of the number ``me``, or False}
        """
        accounts = self.search([
            ('provider', '=', 'web'), ('user_ids', 'in', self.env.uid), ('company_id', 'in', self.env.companies.ids),
        ])
        account = self._om_whatsapp_web_account(me) if me else self.browse()
        if account:
            account._om_whatsapp_web_start()
            now = fields.Datetime.now()
            seen = account.om_whatsapp_web_seen
            if not seen or now - seen >= SEEN_EVERY or account.om_whatsapp_web_seen_user_id != self.env.user:
                # sudo: a user of the account may not write it
                account.sudo().write({'om_whatsapp_web_seen': now, 'om_whatsapp_web_seen_user_id': self.env.uid})
        return {
            'has_account': bool(accounts),
            'account': {'id': account.id, 'name': account.name, 'phone': account.phone or ''} if account else False,
        }

    @api.model
    def om_whatsapp_web_pictures_due(self, me):
        """ The numbers (digits) whose WhatsApp picture the browser reads: the
        recent conversations of the account of ``me`` whose customer has no
        photo in Odoo. """
        account = self._om_whatsapp_web_account(me)
        if not account:
            return []
        return [''.join(char for char in channel.om_whatsapp_number if char.isdigit())
                for channel in account._om_whatsapp_pictures_due()]

    @api.model
    def om_whatsapp_web_set_picture(self, me, phone, data=False, url=False):
        """ The picture the browser read for ``phone``: its data (base64), or
        its address on WhatsApp when the browser could not download it, or
        neither when the customer shows none. """
        account = self._om_whatsapp_web_account(me)
        if not account:
            return False
        if not data and url:
            data = self._om_whatsapp_web_download_picture(url)
        return account._om_whatsapp_set_picture(account._om_whatsapp_format_number(f'+{phone}'), data)

    @api.model
    def _om_whatsapp_web_download_picture(self, url):
        """ A profile picture from the servers of WhatsApp, and from nowhere else. """
        address = urlparse(url)
        host = address.hostname or ''
        if address.scheme != 'https' or not (host == 'whatsapp.net' or host.endswith('.whatsapp.net')):
            return False
        try:
            response = requests.get(url, timeout=PICTURE_TIMEOUT, stream=True)
            response.raise_for_status()
            content = response.raw.read(PICTURE_MAX_SIZE + 1, decode_content=True)
        except requests.RequestException as error:
            _logger.info("WhatsApp picture not downloaded: %s", error)
            return False
        if not content or len(content) > PICTURE_MAX_SIZE:
            return False
        return base64.b64encode(content).decode()

    @api.model
    def om_whatsapp_web_accept(self, me, items):
        """ Which of the messages read in WhatsApp Web Odoo takes: those of a
        number it knows, a contact or a chat it wrote to, and any number when
        the account keeps the unknown ones, never one from before the account
        started. Only their numbers and times come here; the others are
        dropped by the browser.

        :return: {'account': whether ``me`` is an account of the user, 'accept': ids}
        """
        account = self._om_whatsapp_web_account(me)
        if not account:
            return {'account': False, 'accept': []}
        accept = []
        for item in items:
            if item.get('kind') != 'message' or not item.get('phone') or account._om_whatsapp_web_is_old(item):
                continue
            number = account._om_whatsapp_format_number(f"+{item['phone']}")
            if account._om_whatsapp_accepts(number, item.get('quoted_id')):
                accept.append(item['id'])
        return {'account': True, 'accept': accept}

    @api.model
    def om_whatsapp_web_receive(self, me, items):
        """ Record the messages and status updates read in WhatsApp Web. A
        message comes with its file in ``media`` ({name, data}) once the
        browser downloaded it, or ``media_error``. One that fails is logged
        and skipped, the others are kept.

        :return: the number of items recorded
        """
        account = self._om_whatsapp_web_account(me)
        if not account:
            return 0
        done = 0
        for item in items:
            if account._om_whatsapp_web_is_old(item):
                continue
            try:
                with self.env.cr.savepoint():
                    if account._om_whatsapp_receive_item(item):
                        done += 1
            except Exception:
                _logger.exception("WhatsApp Web: %s %s not recorded", item.get('kind'), item.get('id'))
        return done
