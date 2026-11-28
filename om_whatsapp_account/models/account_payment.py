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


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    om_whatsapp_sent = fields.Boolean(
        'Receipt Sent by WhatsApp', readonly=True, copy=False,
        help="The receipt went to the customer by WhatsApp when the payment was confirmed.")

    def _om_whatsapp_template(self):
        self.ensure_one()
        return self.company_id.om_whatsapp_payment_template_id or self.env.ref(
            'om_whatsapp_account.om_whatsapp_template_payment_receipt', raise_if_not_found=False)

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
            },
        }

    def action_post(self):
        res = super().action_post()
        self._om_whatsapp_auto_send()
        return res

    def _om_whatsapp_auto_send(self):
        """ The receipt of the customer payments just confirmed goes by
        WhatsApp, once, when the company sends them. """
        payments = self.filtered(
            lambda p: p.payment_type == 'inbound' and p.partner_type == 'customer' and p.partner_id
            and p.state not in ('draft', 'canceled', 'rejected') and not p.om_whatsapp_sent
            and p.company_id.om_whatsapp_payment_auto)
        if not payments:
            return
        info = payments._phone_get_recipients_info()
        payments = payments.filtered(lambda p: info[p.id]['sanitized'])
        payments.om_whatsapp_sent = True
        for (template, company), batch in payments.grouped(lambda p: (p._om_whatsapp_template(), p.company_id)).items():
            if template:
                send_template(batch, template, company.om_whatsapp_invoice_account_id)
