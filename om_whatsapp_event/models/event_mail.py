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


class EventMail(models.Model):
    _inherit = 'event.mail'

    notification_type = fields.Selection(selection_add=[('om_whatsapp', 'WhatsApp')])
    template_ref = fields.Reference(ondelete={'om.whatsapp.template': 'cascade'},
                                    selection_add=[('om.whatsapp.template', 'WhatsApp')])

    def _compute_notification_type(self):
        super()._compute_notification_type()
        self.filtered(
            lambda s: s.template_ref and s.template_ref._name == 'om.whatsapp.template').notification_type = 'om_whatsapp'

    def _execute_event_based_for_registrations(self, registrations):
        if self.notification_type == 'om_whatsapp':
            self._send_om_whatsapp(registrations)
        return super()._execute_event_based_for_registrations(registrations)

    def _send_om_whatsapp(self, registrations):
        """ WhatsApp the attendees with a valid number, from the account of
        the company of the event; opted-out numbers are skipped. """
        registrations = registrations.filtered(lambda r: r.state not in ('cancel', 'draft'))
        if not registrations:
            return
        info = registrations._phone_get_recipients_info()
        registrations = registrations.filtered(lambda r: info[r.id]['sanitized'])
        template = self.template_ref
        for company, batch in registrations.grouped(lambda r: r.event_id.company_id).items():
            send_template(batch, template, company.om_whatsapp_event_account_id)

    def _template_model_by_notification_type(self):
        info = super()._template_model_by_notification_type()
        info['om_whatsapp'] = 'om.whatsapp.template'
        return info
