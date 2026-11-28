import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    om_ai_whatsapp_conversation_id = fields.Many2one(
        'om.ai.whatsapp.conversation', string='WhatsApp Conversation', readonly=True, copy=False,
        index='btree_not_null', ondelete='set null')
    om_ai_whatsapp_address_set = fields.Boolean('Delivery Address Given on WhatsApp', readonly=True, copy=False)
    om_ai_whatsapp_link_date = fields.Datetime('WhatsApp Payment Link Sent', readonly=True, copy=False)
    om_ai_whatsapp_reminded = fields.Boolean('WhatsApp Payment Reminder Sent', readonly=True, copy=False)

    def action_confirm(self):
        """ The assistant never confirms an order: payment does. """
        if not self.env.su and self.env.user.om_ai_whatsapp_assistant:
            raise AccessError(self.env._('The WhatsApp assistant cannot confirm orders: the payment confirms them.'))
        res = super().action_confirm()
        for order in self.filtered('om_ai_whatsapp_conversation_id'):
            order._om_ai_whatsapp_notify_confirmed()
        return res

    def _om_ai_whatsapp_notify_confirmed(self):
        self.ensure_one()
        conversation = self.om_ai_whatsapp_conversation_id.sudo()
        try:
            with self.env.cr.savepoint():
                lang = conversation._om_ai_lang()
                order = self.sudo().with_context(lang=lang)
                conversation.with_context(lang=lang)._om_ai_send(order.env._(
                    "Thank you! Your payment is received and your order %(order)s is confirmed. We will let you "
                    "know when it ships.", order=order.name))
        except Exception:  # noqa: BLE001 - a WhatsApp message never stops the confirmation
            _logger.exception("WhatsApp confirmation of %s not sent", self.name)

    def _om_ai_whatsapp_amount(self, amount):
        self.ensure_one()
        return formatLang(self.env, amount, currency_obj=self.currency_id)

    def _om_ai_whatsapp_needs_shipping(self):
        self.ensure_one()
        return any(line.product_id.type == 'consu' and not getattr(line, 'is_delivery', False)
                   for line in self.order_line.filtered(lambda l: not l.display_type))

    def _om_ai_whatsapp_ready_error(self):
        """ What is missing before the quotation can go with its payment link. """
        self.ensure_one()
        products = self.order_line.filtered(lambda l: not l.display_type and not getattr(l, 'is_delivery', False))
        if not products:
            return self.env._('The quotation has no product yet.')
        if self.amount_total <= 0:
            return self.env._('The quotation has nothing to pay.')
        if self.partner_id.name in (False, '', self.partner_id.phone):
            return self.env._('Ask the name of the customer first.')
        if self._om_ai_whatsapp_needs_shipping():
            if not self.om_ai_whatsapp_address_set:
                return self.env._('Ask for the delivery address first (wa_set_delivery_address or '
                                  'wa_use_saved_address).')
            carriers = self.sudo().om_ai_whatsapp_conversation_id.account_id.om_ai_carrier_ids
            if carriers and not self.carrier_id:
                return self.env._('Ask the customer to choose a delivery method first (wa_delivery_options).')
        return False

    def _om_ai_whatsapp_summary(self):
        """ The quotation in a few lines, as the customer confirms it. """
        self.ensure_one()
        lines = [self.env._("Quotation %s", self.name)]
        for line in self.order_line.filtered(lambda l: not l.display_type):
            if getattr(line, 'is_delivery', False):
                lines.append(self.env._("Delivery (%(method)s): %(amount)s", method=self.carrier_id.name or line.name,
                                        amount=self._om_ai_whatsapp_amount(line.price_subtotal)))
            else:
                lines.append("%s x %s: %s" % (
                    formatLang(self.env, line.product_uom_qty, digits=2).rstrip('0').rstrip('.,'),
                    line.product_id.display_name, self._om_ai_whatsapp_amount(line.price_subtotal)))
        lines.append(self.env._("Untaxed: %(untaxed)s, taxes: %(taxes)s",
                                untaxed=self._om_ai_whatsapp_amount(self.amount_untaxed),
                                taxes=self._om_ai_whatsapp_amount(self.amount_tax)))
        lines.append(self.env._("*Total: %s*", self._om_ai_whatsapp_amount(self.amount_total)))
        lines.append(self.env._("Name: %s", self.partner_id.name))
        if self.om_ai_whatsapp_address_set:
            shipping = self.partner_shipping_id.sudo()
            conversation = self.sudo().om_ai_whatsapp_conversation_id
            address = shipping._display_address(without_name=True).replace('\n', ', ') \
                if shipping != self.partner_id or conversation.partner_created or conversation._om_ai_level() >= 2 \
                else self.env._('your saved address')
            lines.append(self.env._("Deliver to: %s", address.strip(', ')))
        lines.append(self.env._("Payment: online, by the link sent after your YES."))
        return '\n'.join(lines)

    def _om_ai_whatsapp_status(self, details=False):
        self.ensure_one()
        states = dict(self._fields['state']._description_selection(self.env))
        status = {
            'reference': self.name,
            'date': fields.Datetime.to_string(self.date_order)[:10],
            'status': states.get(self.state),
            'total': self.amount_total,
            'currency': self.currency_id.name,
            'paid_online': self.amount_paid,
            'awaiting_payment': self.state in ('draft', 'sent') and self._has_to_be_paid(),
        }
        if self.state == 'sale':
            status['invoice_status'] = dict(self._fields['invoice_status']._description_selection(self.env)).get(
                self.invoice_status)
        status['deliveries'] = self._om_ai_whatsapp_deliveries()
        if details:
            status['lines'] = [{
                'product': line.product_id.display_name, 'quantity': line.product_uom_qty,
                'delivered': line.qty_delivered, 'subtotal': line.price_subtotal,
            } for line in self.order_line.filtered(lambda l: not l.display_type)]
        return status

    def _om_ai_whatsapp_deliveries(self):
        """ The deliveries of the order with their tracking, when the
        inventory is installed. A carrier connector adds its tracking link to
        the pickings (carrier_tracking_ref, carrier_tracking_url). """
        self.ensure_one()
        if 'picking_ids' not in self._fields:
            return []
        result = []
        for picking in self.sudo().picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing'):
            states = dict(picking._fields['state']._description_selection(self.env))
            item = {
                'reference': picking.name,
                'status': states.get(picking.state),
                'scheduled': picking.scheduled_date and fields.Datetime.to_string(picking.scheduled_date)[:10],
                'done': picking.date_done and fields.Datetime.to_string(picking.date_done)[:10],
            }
            for name in ('carrier_tracking_ref', 'carrier_tracking_url'):
                if name in picking._fields and picking[name]:
                    item[name.replace('carrier_', '')] = picking[name]
            result.append(item)
        return result

    @api.model
    def _cron_om_ai_whatsapp_reminders(self):
        """ One reminder with the payment link when a quotation sent by the
        assistant is still unpaid after the hours of its account. """
        orders = self.sudo().search([
            ('om_ai_whatsapp_conversation_id', '!=', False), ('om_ai_whatsapp_link_date', '!=', False),
            ('om_ai_whatsapp_reminded', '=', False), ('state', 'in', ('draft', 'sent')),
        ], limit=200)
        now = fields.Datetime.now()
        for order in orders:
            conversation = order.om_ai_whatsapp_conversation_id
            hours = conversation.account_id.om_ai_reminder_hours
            if not hours or order.om_ai_whatsapp_link_date > now - timedelta(hours=hours):
                continue
            order.om_ai_whatsapp_reminded = True
            if not conversation.account_id.om_ai_active or not order._has_to_be_paid() or order.is_expired:
                continue
            lang = conversation._om_ai_lang()
            order = order.with_context(lang=lang)
            link = self.env['payment.link.wizard'].sudo().with_context(
                active_model='sale.order', active_id=order.id).create({}).link
            conversation.with_context(lang=lang)._om_ai_send(order.env._(
                "A friendly reminder: your quotation %(order)s (%(amount)s) is waiting for payment. Pay online "
                "here to confirm your order:\n%(link)s",
                order=order.name, amount=order._om_ai_whatsapp_amount(order.amount_total), link=link))
            order.message_post(body=order.env._('Payment reminder sent on WhatsApp.'), subtype_xmlid='mail.mt_note')
