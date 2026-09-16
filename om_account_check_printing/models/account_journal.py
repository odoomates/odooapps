from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    check_format_id = fields.Many2one(
        'account.check.format', string='Cheque Format', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Where the fields are printed on the cheques of this bank account.",
    )

    def _get_check_format(self):
        """ :return: the cheque format of the journal, else the first one of its company """
        self.ensure_one()
        return self.check_format_id or self.env['account.check.format'].search([
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ], limit=1)
