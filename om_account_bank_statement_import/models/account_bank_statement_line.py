from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    unique_import_id = fields.Char(
        string='Import ID', readonly=True, copy=False, index='btree_not_null',
        help="The identifier of the transaction in the file it was imported from: a transaction already "
             "imported in the journal is not imported again.")

    _unique_import_id_uniq = models.Constraint(
        'UNIQUE(unique_import_id)',
        'A transaction of a bank statement file is only imported once.',
    )
