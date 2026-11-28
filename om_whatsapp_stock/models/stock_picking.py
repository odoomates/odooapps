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


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    om_whatsapp_done_sent = fields.Boolean(
        'Sent by WhatsApp When Done', readonly=True, copy=False,
        help="The transfer went to its contact by WhatsApp when it was done.")

    def om_whatsapp_tracking(self):
        """ The tracking number and link of the carrier, as a sentence, when
        the transfer has them. """
        self.ensure_one()
        self.check_access('read')
        reference = self['carrier_tracking_ref'] if 'carrier_tracking_ref' in self._fields else False
        url = self['carrier_tracking_url'] if 'carrier_tracking_url' in self._fields else False
        if url and reference:
            return self.env._("Tracking number %(reference)s, follow it here: %(url)s", reference=reference, url=url)
        if url:
            return self.env._("Follow it here: %(url)s", url=url)
        if reference:
            carrier = self['carrier_id'].name if 'carrier_id' in self._fields and self['carrier_id'] else False
            if carrier:
                return self.env._("%(carrier)s tracking number: %(reference)s.", carrier=carrier, reference=reference)
            return self.env._("Tracking number: %(reference)s.", reference=reference)
        return self.env._("It is on its way to you.")

    def _om_whatsapp_template(self):
        """ The template of the Send by WhatsApp button: shipped once done,
        out for delivery before. """
        self.ensure_one()
        if self.state == 'done':
            return self.picking_type_id.om_whatsapp_done_template_id or self.env.ref(
                'om_whatsapp_stock.om_whatsapp_template_delivery_done', raise_if_not_found=False)
        return self.env.ref('om_whatsapp_stock.om_whatsapp_template_out_for_delivery', raise_if_not_found=False)

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

    def _send_confirmation_email(self):
        """ After the confirmation (and the label of the carrier, which gives
        the tracking number), the WhatsApp of the operation type. """
        res = super()._send_confirmation_email()
        self._om_whatsapp_auto_send()
        return res

    def _om_whatsapp_auto_send(self):
        pickings = self.filtered(lambda p: p.state == 'done' and not p.om_whatsapp_done_sent and p.partner_id
                                 and p.picking_type_id.om_whatsapp_done_template_id)
        if not pickings:
            return
        info = pickings._phone_get_recipients_info()
        pickings = pickings.filtered(lambda p: info[p.id]['sanitized'])
        pickings.om_whatsapp_done_sent = True
        for (template, company), batch in pickings.grouped(
                lambda p: (p.picking_type_id.om_whatsapp_done_template_id, p.company_id)).items():
            send_template(batch, template, company.om_whatsapp_stock_account_id)
