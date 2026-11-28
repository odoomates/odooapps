from odoo import api, fields, models


class FollowupFollowup(models.Model):
    _inherit = 'followup.followup'

    om_whatsapp_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string='WhatsApp Account',
        help="The account the WhatsApp reminders of this plan are sent from. Empty: the account of the template, "
             "else the one of the user sending them.")


class FollowupLine(models.Model):
    _inherit = 'followup.line'

    send_whatsapp = fields.Boolean(
        'Send a WhatsApp', help="When processing, it sends a WhatsApp message to the customer, with the amount "
                                "overdue and the overdue invoices with their payment links.")
    whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', 'WhatsApp Template', domain="[('model', '=', 'res.partner')]",
        default=lambda self: self._om_whatsapp_default_template(),
        help="The message sent by WhatsApp. Empty: the payment reminder of the follow-ups.")

    @api.model
    def _om_whatsapp_default_template(self):
        return self.env.ref('om_whatsapp_followup.om_whatsapp_template_followup', raise_if_not_found=False)
