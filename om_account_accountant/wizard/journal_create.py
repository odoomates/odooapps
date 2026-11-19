from odoo import api, fields, models, _

JOURNAL_TYPES = [
    ('bank', 'Bank'),
    ('credit', 'Credit Card'),
    ('cash', 'Cash'),
    ('sale', 'Sales'),
    ('purchase', 'Purchase'),
    ('general', 'Miscellaneous'),
]


class OmJournalCreate(models.TransientModel):
    """ A journal created from what it is for: its name, its short code and, for a bank, its account number;
    the accounts of the journal are created as when a journal of that type is created by hand. """
    _name = 'om.journal.create'
    _description = 'New Journal'

    journal_type = fields.Selection(JOURNAL_TYPES, string='Journal For', required=True, default='bank')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    name = fields.Char(string='Name', compute='_compute_name', store=True, readonly=False, required=True)
    code = fields.Char(string='Short Code', compute='_compute_code', store=True, readonly=False, required=True,
                       size=5, help='The prefix of the numbers of its entries.')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  help='Leave empty for the currency of the company.')
    bank_account_number = fields.Char(string='Account Number')
    bank_bic = fields.Char(string='BIC')

    @api.depends('journal_type')
    def _compute_name(self):
        labels = dict(JOURNAL_TYPES)
        for wizard in self:
            wizard.name = _(labels[wizard.journal_type]) if wizard.journal_type else False

    @api.depends('journal_type', 'company_id')
    def _compute_code(self):
        prefixes = {'bank': 'BNK', 'credit': 'CARD', 'cash': 'CSH', 'sale': 'INV', 'purchase': 'BILL', 'general': 'MISC'}
        Journal = self.env['account.journal'].with_context(active_test=False)
        for wizard in self:
            prefix = prefixes.get(wizard.journal_type, 'JRNL')
            used = set(Journal.search([('company_id', '=', wizard.company_id.id)]).mapped('code'))
            code, index = prefix, 1
            while code in used:
                index += 1
                code = '%s%s' % (prefix[:5 - len(str(index))], index)
            wizard.code = code

    def action_create(self):
        self.ensure_one()
        vals = {
            'name': self.name,
            'code': self.code,
            'type': self.journal_type,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
        }
        if self.journal_type == 'bank' and self.bank_account_number:
            vals.update(bank_account_number=self.bank_account_number, bank_bic=self.bank_bic)
        journal = self.env['account.journal'].create(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.journal',
            'res_id': journal.id,
            'views': [(False, 'form')],
            'target': 'current',
        }
