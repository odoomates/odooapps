from odoo import api, fields, models


class OmTallyCheckLine(models.Model):
    """ One account of the trial balance check: Tally's balance next to what the import posts. """
    _name = 'om.tally.check.line'
    _description = 'Tally Trial Balance Check'
    _order = 'is_explained, abs_difference desc, label'

    import_id = fields.Many2one('om.tally.import', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='import_id.currency_id')
    account_id = fields.Many2one('account.account', string='Odoo Account', ondelete='set null')
    label = fields.Char(string='Account')
    ledger_names = fields.Char(string='Tally Ledgers')
    tally_balance = fields.Monetary(string='Tally')
    posted_balance = fields.Monetary(string='Odoo after Import')
    existing_balance = fields.Monetary(string='Already in Odoo',
                                       help="What Odoo holds on this account before the cut-over date, outside this "
                                            "import: not zero means the account was already used.")
    difference = fields.Monetary(compute='_compute_difference', store=True)
    abs_difference = fields.Monetary(compute='_compute_difference', store=True)
    note = fields.Char()
    is_explained = fields.Boolean(string='Explained', help="A difference that comes from an option you chose.")

    @api.depends('tally_balance', 'posted_balance')
    def _compute_difference(self):
        for line in self:
            line.difference = line.currency_id.round(line.tally_balance - line.posted_balance) \
                if line.currency_id else line.tally_balance - line.posted_balance
            line.abs_difference = abs(line.difference)
