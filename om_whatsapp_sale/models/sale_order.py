from odoo import fields, models


def send_template(records, template, account):
    """ Send ``template`` from ``records`` without a user at the screen. With
    no account to send from, the documents say so in their chatter. """
    account = account or template.account_id or records.env['om.social.account']._get_default_account('whatsapp')
    if not account:
        for record in records:
            record._message_log(body=records.env._(
                "The WhatsApp %(template)s was not sent: choose the WhatsApp account to send from in the settings.",
                template=template.name))
        return records.env['mail.message']
    return records._message_om_whatsapp_template(template.sudo(), account=account)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    om_whatsapp_confirm_sent = fields.Boolean(
        'Confirmation Sent by WhatsApp', readonly=True, copy=False,
        help="The confirmation went to the customer by WhatsApp when the order was confirmed.")

    def _om_whatsapp_template(self):
        """ The template of the Send by WhatsApp button: the quotation, or the
        confirmation of an order. """
        self.ensure_one()
        company = self.company_id
        if self.state == 'sale':
            return self._om_whatsapp_confirm_template()
        return company.om_whatsapp_quotation_template_id or self.env.ref(
            'om_whatsapp_sale.om_whatsapp_template_quotation', raise_if_not_found=False)

    def _om_whatsapp_confirm_template(self):
        """ The template of the confirmation; an online shop may have its
        own. """
        self.ensure_one()
        return self.company_id.om_whatsapp_order_template_id or self.env.ref(
            'om_whatsapp_sale.om_whatsapp_template_order_confirmed', raise_if_not_found=False)

    def _om_whatsapp_confirm_auto(self):
        """ Whether the confirmation of this order goes by WhatsApp by
        itself. """
        self.ensure_one()
        return self.company_id.om_whatsapp_order_auto

    def _om_whatsapp_account(self):
        self.ensure_one()
        return self.company_id.om_whatsapp_sale_account_id

    def om_whatsapp_portal_link(self):
        """ The full link of the order on the customer portal, where it is
        viewed, signed and paid online. """
        self.ensure_one()
        self.check_access('read')
        return self.get_base_url() + self.get_portal_url()

    def action_om_whatsapp_send(self):
        template = self[:1]._om_whatsapp_template() if self else False
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Send by WhatsApp"),
            'res_model': 'om.whatsapp.composer',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'active_model': self._name,
                'active_ids': self.ids,
                'active_id': self[:1].id,
                'default_template_id': template.id if template else False,
                'om_whatsapp_mark_so_sent': True,
            },
        }

    def _message_om_social(self, account, body, address, partner=False, failure_type=False, failure_reason=False,
                           status='ready', **post_values):
        """ A quotation sent by WhatsApp from its button is sent, as by email;
        one that could not go stays a draft. """
        if self.env.context.get('om_whatsapp_mark_so_sent') and not failure_type:
            self.filtered(lambda order: order.state == 'draft').with_context(tracking_disable=True).write(
                {'state': 'sent'})
        return super()._message_om_social(account, body, address, partner=partner, failure_type=failure_type,
                                          failure_reason=failure_reason, status=status, **post_values)

    def action_confirm(self):
        res = super().action_confirm()
        self._om_whatsapp_auto_send()
        return res

    def _om_whatsapp_auto_send(self):
        """ The orders just confirmed go by WhatsApp, once, when the company
        sends the confirmations. An order of the WhatsApp assistant is
        confirmed to the customer in its own conversation. """
        orders = self.filtered(
            lambda o: o.state == 'sale' and not o.om_whatsapp_confirm_sent and o._om_whatsapp_confirm_auto()
            and o.partner_id and not o._om_whatsapp_has_own_confirmation())
        if not orders:
            return
        info = orders._phone_get_recipients_info()
        orders = orders.filtered(lambda o: info[o.id]['sanitized'])
        orders.om_whatsapp_confirm_sent = True
        for (template, account), batch in orders.grouped(
                lambda o: (o._om_whatsapp_confirm_template(), o._om_whatsapp_account())).items():
            if template:
                send_template(batch, template, account)

    def _om_whatsapp_has_own_confirmation(self):
        self.ensure_one()
        return bool('om_ai_whatsapp_conversation_id' in self._fields and self.om_ai_whatsapp_conversation_id)
