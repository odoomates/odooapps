from odoo import api, fields, models

# the products named in the reminder of a cart, the others counted
MAX_PRODUCTS = 3


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

    om_whatsapp_cart_sent = fields.Boolean(
        'Cart Reminder Sent by WhatsApp', readonly=True, copy=False,
        help="The abandoned cart got its WhatsApp reminder, or was checked and gets none: it is never sent twice.")

    def _om_whatsapp_confirm_auto(self):
        self.ensure_one()
        return super()._om_whatsapp_confirm_auto() or bool(self.website_id.om_whatsapp_order_template_id)

    def _om_whatsapp_confirm_template(self):
        self.ensure_one()
        return self.website_id.om_whatsapp_order_template_id or super()._om_whatsapp_confirm_template()

    def om_whatsapp_cart_link(self):
        """ The link that opens the cart again, for the customer. """
        self.ensure_one()
        self.check_access('read')
        return f'{self.get_base_url()}/shop/cart?id={self.id}&access_token={self._portal_ensure_token()}'

    def om_whatsapp_cart_products(self):
        """ The products of the cart on one line. """
        self.ensure_one()
        self.check_access('read')
        names = self.website_order_line.product_id.mapped('name')
        text = ', '.join(names[:MAX_PRODUCTS])
        if len(names) > MAX_PRODUCTS:
            text = self.env._("%(products)s and %(count)s more", products=text, count=len(names) - MAX_PRODUCTS)
        return text or '-'

    @api.model
    def _cron_om_whatsapp_abandoned_carts(self, limit=200):
        """ One WhatsApp reminder for each cart left by a signed-in customer,
        after the delay of the abandoned carts of its website, as the email
        reminder does: not for a cart with a failed payment, free, out of
        stock, or followed by an order. A cart without a valid number is
        skipped; an opted-out number gets nothing. """
        websites = self.env['website'].search([
            ('send_abandoned_cart_followup', '=', True), ('om_whatsapp_cart_template_id', '!=', False),
            ('om_whatsapp_cart_since', '!=', False),
        ])
        for website in websites:
            carts = self.search([
                ('is_abandoned_cart', '=', True),
                ('website_id', '=', website.id),
                ('om_whatsapp_cart_sent', '=', False),
                ('date_order', '>=', website.om_whatsapp_cart_since),
            ], limit=limit)
            if not carts:
                continue
            ready = carts._filter_can_send_abandoned_cart_followup()
            if ready:
                info = ready._phone_get_recipients_info()
                ready = ready.filtered(lambda cart: info[cart.id]['sanitized'])
            carts.om_whatsapp_cart_sent = True
            if ready:
                send_template(ready, website.om_whatsapp_cart_template_id, website.company_id.om_whatsapp_sale_account_id)
            if self.env.context.get('cron_id'):
                self.env['ir.cron']._commit_progress(len(carts))
