from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    pdc_receivable_account_id = fields.Many2one(
        'account.account', string='PDC Receivable Account', domain="[('active', '=', True)]",
        help="A current asset holding the cheques received until they are cleared. Allow reconciliation on it.")
    pdc_payable_account_id = fields.Many2one(
        'account.account', string='PDC Payable Account', domain="[('active', '=', True)]",
        help="A current liability holding the cheques issued until they are cleared. Allow reconciliation on it.")
    pdc_journal_id = fields.Many2one(
        'account.journal', string='PDC Journal', domain="[('type', '=', 'general')]",
        help="The journal of the registration of the cheques; the clearing goes to their bank journal.")
