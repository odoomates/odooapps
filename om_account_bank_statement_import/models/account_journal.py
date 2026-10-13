from odoo import _, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    statement_import_map_id = fields.Many2one(
        'account.statement.import.map', string='Statement File Map', check_company=True,
        help="The columns of the CSV or Excel statements of this bank, filled in by default when importing.")

    def action_import_statement(self):
        """ Import a statement file in this journal, from its card of the dashboard """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Statement'),
            'res_model': 'account.statement.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.id},
        }
