from odoo import fields, models

CASH_FLOW_ACTIVITIES = [
    ('operating', 'Operating Activities'),
    ('investing', 'Investing Activities'),
    ('financing', 'Financing Activities'),
]


class AccountAccount(models.Model):
    _inherit = 'account.account'

    cash_flow_activity = fields.Selection(
        CASH_FLOW_ACTIVITIES, string='Cash Flow Activity',
        help="Section of the Cash Flow Statement for the cash paid or received against this account. "
             "Leave empty to use the section of its type: fixed and non-current assets are investing, "
             "non-current liabilities and equity are financing, the others are operating.",
    )
