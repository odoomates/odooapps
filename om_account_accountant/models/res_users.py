from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_invoice_signature_image = fields.Image(
        string='Signature on Invoices', max_width=600, max_height=240,
        help='Your handwritten signature, printed on the invoices you sign.')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['om_invoice_signature_image']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['om_invoice_signature_image']
