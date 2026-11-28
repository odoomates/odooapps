from odoo import fields, models

TEMPLATE_DOMAIN = "[('model', '=', 'project.task')]"


class ResCompany(models.Model):
    _inherit = 'res.company'

    fs_whatsapp_account_id = fields.Many2one(
        'om.social.account', string="Field Service WhatsApp Account", domain="[('channel', '=', 'whatsapp')]",
        help="Account the job messages are sent from. Empty: the account of the template, else the one of "
             "the user.")
    fs_whatsapp_planned_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp: Job Planned", domain=TEMPLATE_DOMAIN,
        help="Sent to the customer when the job is planned. Empty: no message.")
    fs_whatsapp_on_the_way_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp: Technician on the Way", domain=TEMPLATE_DOMAIN,
        help="Sent to the customer when the technician starts travelling. Empty: no message.")
    fs_whatsapp_report_id = fields.Many2one(
        'om.whatsapp.template', string="WhatsApp: Job Done", domain=TEMPLATE_DOMAIN,
        help="Sent to the customer with the job report when the job is done. Empty: no message.")
