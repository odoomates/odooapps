from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    check_format_id = fields.Many2one(
        'account.check.format', string='Cheque Format', check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Where the fields are printed on the cheques of this bank account.",
    )

    def _get_check_format(self):
        """ :return: the cheque format of the journal, else the first one of its company, preferring the formats
                     of the country of the company """
        self.ensure_one()
        if self.check_format_id:
            return self.check_format_id
        formats = self.env['account.check.format'].search([
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ])
        country = self.company_id.country_id
        return (formats.filtered(lambda check_format: country in check_format.country_ids)[:1]
                or formats.filtered(lambda check_format: not check_format.country_ids)[:1]
                or formats[:1])
