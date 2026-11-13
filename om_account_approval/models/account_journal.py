from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    om_skip_approval = fields.Boolean(
        string='Post Without Approval',
        help='The entries of this journal never wait for an approval, e.g. the journals of the depreciation, '
             'the currency revaluation or the year-end closing, posted by Odoo itself.')
