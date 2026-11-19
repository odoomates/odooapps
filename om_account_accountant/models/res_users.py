from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_invoice_signature_image = fields.Image(
        string='Signature on Invoices', max_width=600, max_height=240, user_writeable=True,
        help='Your handwritten signature, printed on the invoices you sign.')
