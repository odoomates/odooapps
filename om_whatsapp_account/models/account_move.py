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


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_whatsapp_sent = fields.Boolean(
        'Sent by WhatsApp on Posting', readonly=True, copy=False,
        help="The invoice went to the customer by WhatsApp when it was posted: it is not sent again on a new posting.")

    def _om_whatsapp_template(self):
        """ The WhatsApp template of an invoice or a credit note. """
        self.ensure_one()
        company = self.company_id
        if self.move_type == 'out_refund':
            return company.om_whatsapp_refund_template_id or self.env.ref(
                'om_whatsapp_account.om_whatsapp_template_credit_note', raise_if_not_found=False)
        return company.om_whatsapp_invoice_template_id or self.env.ref(
            'om_whatsapp_account.om_whatsapp_template_invoice', raise_if_not_found=False)

    def om_whatsapp_portal_link(self):
        """ The full link of the invoice on the customer portal, where it is
        viewed, downloaded and paid online. """
        self.ensure_one()
        self.check_access('read')
        return self.get_base_url() + self.get_portal_url()

    def action_om_whatsapp_send(self):
        """ The composer, with the template of the invoice and its PDF. """
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

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._om_whatsapp_auto_send()
        return posted

    def _om_whatsapp_auto_send(self):
        """ The customer invoices and credit notes just posted go by WhatsApp,
        once, when the company sends them on posting. A customer without a
        valid number gets nothing; a sending problem never stops the
        posting. """
        moves = self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund') and not m.om_whatsapp_sent
                              and m.company_id.om_whatsapp_invoice_auto and m.partner_id)
        if not moves:
            return
        info = moves._phone_get_recipients_info()
        moves = moves.filtered(lambda m: info[m.id]['sanitized'])
        moves.om_whatsapp_sent = True
        for (template, company), batch in moves.grouped(lambda m: (m._om_whatsapp_template(), m.company_id)).items():
            if template:
                send_template(batch, template, company.om_whatsapp_invoice_account_id)
