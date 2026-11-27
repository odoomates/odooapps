import base64
import re
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# what a status or an ack of WhatsApp means for a message sent
ITEM_STATUS = {'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed', 2: 'delivered', 3: 'read', 4: 'read'}
# kinds of messages with a file, named when the file could not be read
MEDIA_LABELS = {
    'image': _lt("Picture"),
    'document': _lt("Document"),
    'sticker': _lt("Sticker"),
    'ptt': _lt("Voice message"),
    'audio': _lt("Audio"),
    'video': _lt("Video"),
}

# a WhatsApp user ID: the country of the user, a dot, letters and digits (US.13491208655302741918, US.ENT.1234)
USER_ID = re.compile(r'^[A-Z]{2}\.[A-Za-z0-9.]+$')


class OmSocialAccount(models.Model):
    """ A WhatsApp number of the Social Inbox. The provider decides how a
    message leaves Odoo: provider modules add their key to ``provider`` and
    implement ``_om_social_send_<provider>``; WhatsApp ships Click to Chat,
    which opens the chat in a new tab with the text filled in. The address of
    a customer is their phone number, as WhatsApp gives it: the + and the
    digits. """
    _inherit = 'om.social.account'

    provider = fields.Selection(selection_add=[('link', 'Click to Chat')], default='link', ondelete={'link': 'cascade'})
    phone = fields.Char('WhatsApp Number', related='address', readonly=False,
                        help="The number this account sends from, shown to the users.")

    def _om_social_format_address(self, address):
        self.ensure_one()
        if self.channel != 'whatsapp' or not address or self._om_social_is_user_ref(address):
            return super()._om_social_format_address(address)
        return self._om_social_clean_address(
            self.env.user._phone_format(number=address, country=self.company_id.country_id) or address)

    @api.model
    def _om_social_clean_address(self, address):
        """ A number as conversations and messages keep it: the + and the
        digits. Without the phonenumbers library, Odoo leaves a number as
        typed; +32 470 55 51 23 and +32470555123 are one customer. A user ID
        stays as it is. """
        if (self and any(account.channel != 'whatsapp' for account in self)) or not address \
                or self._om_social_is_user_ref(address.strip()):
            return super()._om_social_clean_address(address)
        return re.sub(r'(?!^\+)[^\d]', '', address.strip())

    @api.model
    def _om_social_is_user_ref(self, address):
        """ Whether ``address`` is a WhatsApp user ID rather than a number. """
        return bool(address and USER_ID.match(address)) or super()._om_social_is_user_ref(address)

    def _om_social_find_partner_by_address(self, address):
        """ The contact of the number: by their phone. """
        self.ensure_one()
        if self.channel != 'whatsapp':
            return super()._om_social_find_partner_by_address(address)
        Partner = self.env['res.partner'].sudo()
        domain = [('company_id', 'in', [False, self.company_id.id])]
        partner = Partner.search([('phone_sanitized', '=', address), *domain], limit=1)
        if not partner:
            # without the phonenumbers library, a phone keeps its spaces: compared without them
            partner = Partner.search([('phone_mobile_search', '=', address), *domain], limit=1)
        return partner or super()._om_social_find_partner_by_address(address)

    def _om_social_send_link(self, notifications):
        """ Click to Chat cannot tell whether the user pressed send, so the
        message counts as sent once the chat is open. """
        notifications._om_social_set_status('sent')
        digits = ''.join(char for char in notifications.om_social_address if char.isdigit())
        return {
            'type': 'ir.actions.act_url',
            'url': f'https://wa.me/{digits}?text={quote(notifications.mail_message_id._om_social_text())}',
            'target': 'new',
            'close': True,
        }

    # ------------------------------------------------------------
    # RECEIVING, as the WhatsApp providers give it
    # ------------------------------------------------------------

    def _om_whatsapp_receive(self, number, body='', whatsapp_id=False, attachments=None, quoted_id=False, from_me=False,
                             profile_name=False, voice=False, user_id=False, username=False):
        """ Record a WhatsApp message of a chat of this account, received from
        ``number`` or sent to it from the phone when ``from_me``: see
        ``_om_social_receive``. ``user_id`` is the WhatsApp user ID of the
        customer for this business and ``username`` their WhatsApp username,
        when the provider gives them; ``number`` may then be empty. A provider
        may give both in the context instead (``om_whatsapp_user_id``,
        ``om_whatsapp_username``), which keeps the modules that extend this
        method with fewer arguments working.

        :return: the mail.message of the conversation, or False when skipped
        """
        self.ensure_one()
        user_id = user_id or self.env.context.get('om_whatsapp_user_id') or False
        username = username or self.env.context.get('om_whatsapp_username') or False
        return self._om_social_receive(
            number, body, message_id=whatsapp_id, attachments=attachments, quoted_id=quoted_id, from_me=from_me,
            profile_name=profile_name, voice=voice, user_ref=user_id, username=username)

    def _om_whatsapp_receive_item(self, item):
        """ One item read from WhatsApp by a provider (the browser extension,
        the WhatsApp Bridge): a message, the status of one sent, a reaction.
        A message has its file in ``media`` ({name, data}, base64), or
        ``media_error``.

        :return: whether it was recorded
        """
        self.ensure_one()
        if item.get('kind') == 'status':
            status = ITEM_STATUS.get(item.get('status') or item.get('ack'))
            return bool(status and self._om_social_update_status(item['id'], status))
        if item.get('kind') == 'reaction':
            return self._om_social_receive_reaction(
                f"+{item.get('phone')}", item.get('message_id'), item.get('emoji'), from_me=bool(item.get('from_me')))
        if item.get('kind') != 'message' or not item.get('phone') or not item.get('id'):
            return False
        lines = [item.get('body') or '']
        if item.get('note'):
            lines.insert(0, f"[{item['note']}]")
        attachments = []
        if media := item.get('media'):
            attachments.append((media['name'], base64.b64decode(media['data'])))
        elif item.get('media_error'):
            if label := MEDIA_LABELS.get(item.get('type')):
                lines.insert(0, f"[{label}]")
            lines.append(_("(The file could not be read from WhatsApp: %(reason)s)", reason=item['media_error']))
        return bool(self._om_whatsapp_receive(
            f"+{item['phone']}",
            '\n'.join(line for line in lines if line),
            whatsapp_id=item['id'],
            attachments=attachments,
            quoted_id=item.get('quoted_id') or False,
            from_me=bool(item.get('from_me')),
            profile_name=item.get('name') or False,
            voice=item.get('type') == 'ptt' and bool(attachments),
        ))
