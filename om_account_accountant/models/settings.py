from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    credit_limit_block = fields.Boolean(
        related="company_id.credit_limit_block", readonly=False)
    om_invoice_signature = fields.Boolean(related="company_id.om_invoice_signature", readonly=False)
    om_invoice_signer_id = fields.Many2one(related="company_id.om_invoice_signer_id", readonly=False)
    anglo_saxon_accounting = fields.Boolean(
        related="company_id.anglo_saxon_accounting",
        readonly=False, string="Use anglo-saxon accounting",
        help="Record the cost of a good as an expense when this good is invoiced to a final customer."
    )
