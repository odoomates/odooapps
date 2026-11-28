import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    om_ai_whatsapp_shipping_sent = fields.Datetime('WhatsApp Shipping Message Sent', readonly=True, copy=False)

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            picking._om_ai_whatsapp_notify_shipping()
        return res

    def _om_ai_whatsapp_tracking_links(self):
        """ The tracking links of the delivery: one, or one per parcel with
        the carriers that track parcels apart. """
        self.ensure_one()
        multiple = self.get_multiple_carrier_tracking() if self.carrier_tracking_url else False
        if isinstance(multiple, list):
            return [entry[1] for entry in multiple if isinstance(entry, (list, tuple)) and len(entry) > 1]
        return [self.carrier_tracking_url] if self.carrier_tracking_url else []

    def _om_ai_whatsapp_shipping_conversation(self):
        """ The WhatsApp conversation of the order of this delivery, when it
        should get a shipping message now. """
        self.ensure_one()
        picking = self.sudo()
        if picking.state != 'done' or picking.picking_type_code != 'outgoing' or picking.om_ai_whatsapp_shipping_sent:
            return None
        conversation = picking.sale_id.om_ai_whatsapp_conversation_id
        account = conversation.account_id
        if not conversation or not account.om_ai_active or not account.om_ai_shipping_messages:
            return None
        return conversation

    def _om_ai_whatsapp_shipping_text(self, conversation):
        self.ensure_one()
        picking = self.sudo()
        lang = conversation._om_ai_lang()
        account = conversation.account_id.with_context(lang=lang)
        tracking = ' '.join(picking._om_ai_whatsapp_tracking_links()) or picking.carrier_tracking_ref or ''
        values = {
            'order': picking.sale_id.name or '',
            'delivery': picking.name or '',
            'carrier': picking.carrier_id.with_context(lang=lang).name or self.env._('our delivery team'),
            'tracking': tracking,
        }
        lines = []
        for line in (account.om_ai_shipping_text or '').split('\n'):
            filled = line
            for key, value in values.items():
                filled = filled.replace('{%s}' % key, value)
            if filled.strip() or not line.strip():
                lines.append(filled)
        return '\n'.join(lines).strip()

    def _om_ai_whatsapp_notify_shipping(self):
        """ Tell the customer on WhatsApp that the delivery left, once. A send
        that fails never stops the validation. """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                conversation = self._om_ai_whatsapp_shipping_conversation()
                if not conversation:
                    return
                picking = self.sudo()
                picking.om_ai_whatsapp_shipping_sent = fields.Datetime.now()
                if conversation.state == 'stopped' or conversation._om_ai_is_opted_out():
                    picking.message_post(body=self.env._(
                        'No WhatsApp shipping message: the customer opted out.'), subtype_xmlid='mail.mt_note')
                    return
                text = picking._om_ai_whatsapp_shipping_text(conversation)
                if not text:
                    return
                conversation._om_ai_send(text)
                if conversation.state == 'human':
                    conversation._om_ai_note(self.env._(
                        'Shipping message of %s sent while a person handles the conversation.', picking.name))
                picking.message_post(body=self.env._('Shipping message sent on WhatsApp.'),
                                     subtype_xmlid='mail.mt_note')
        except Exception:  # noqa: BLE001 - a WhatsApp message never blocks the validation
            _logger.exception("WhatsApp shipping message of %s not sent", self.name)
