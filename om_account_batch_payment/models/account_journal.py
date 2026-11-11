from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    om_batch_layout_id = fields.Many2one(
        'account.batch.payment.layout', string='Bank File Layout', check_company=True,
        help="The layout of the file of the batch payments uploaded to this bank.")
