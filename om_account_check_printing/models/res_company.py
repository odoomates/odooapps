from odoo import fields, models

CHECK_FORMAT_LAYOUT = 'om_account_check_printing.action_report_check'


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_check_printing_layout = fields.Selection(
        selection_add=[(CHECK_FORMAT_LAYOUT, 'Configurable Cheque Format')],
        ondelete={CHECK_FORMAT_LAYOUT: 'set default'},
    )
