from odoo import fields, models


class PrintTemplate(models.Model):
    _inherit = 'print.template'

    sign_role_ids = fields.One2many('sign.role', 'template_id', string='Signers', copy=True)
    sign_email_code = fields.Boolean(
        string='Email Code',
        help='Each signer gets a code by email and enters it before signing: proof that the signature comes from '
             'the owner of the email address, e.g. for contracts and offers.')
    sign_validity_days = fields.Integer(
        string='Days to Sign', default=14, help='The request expires after these days. 0 for no deadline.')
    sign_reminder_days = fields.Integer(
        string='Remind Every', default=3, help='Days between the reminders to a signer. 0 for no reminder.')
