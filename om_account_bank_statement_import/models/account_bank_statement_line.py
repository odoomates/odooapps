from odoo import fields, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    unique_import_id = fields.Char(
        string='Import ID', readonly=True, copy=False,
        help="The identifier of the transaction in the file it was imported from: a transaction already "
             "imported in the journal is not imported again.")

    _sql_constraints = [
        # the name of the constraint of the import of 15.0 before the maps
        ('unique_import_id', 'UNIQUE(unique_import_id)',
         'A transaction of a bank statement file is only imported once.'),
    ]
