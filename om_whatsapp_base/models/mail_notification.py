from odoo import fields, models


class MailNotification(models.Model):
    _inherit = 'mail.notification'

    failure_type = fields.Selection(selection_add=[
        ('om_whatsapp_number', 'No Valid Number'),
        ('om_whatsapp_optout', 'Number Opted Out'),
    ])
