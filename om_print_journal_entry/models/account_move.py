from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def om_print_document_label(self):
        """ The kind of document, as the print names it: Journal Entry, Customer Invoice, Vendor Bill... """
        self.ensure_one()
        return dict(self._fields['move_type']._description_selection(self.env)).get(self.move_type, '')

    def om_print_has_taxes(self):
        self.ensure_one()
        return any(line.tax_ids or line.tax_line_id for line in self.line_ids)

    def om_print_has_foreign_currency(self):
        self.ensure_one()
        return any(line.currency_id and line.currency_id != self.company_currency_id for line in self.line_ids)

    def om_print_tax_summary(self):
        """ Base and amount of each tax of the entry, in the company currency """
        self.ensure_one()
        summary = {}
        for line in self.line_ids.filtered('tax_line_id'):
            entry = summary.setdefault(line.tax_line_id.id, {'name': line.tax_line_id.name, 'base': 0.0, 'amount': 0.0})
            entry['base'] += abs(line.tax_base_amount)
            entry['amount'] += abs(line.balance)
        return list(summary.values())


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def om_print_tax_labels(self):
        """ The taxes of a line, or the tax a tax line is for """
        self.ensure_one()
        names = self.tax_ids.mapped('name')
        if self.tax_line_id:
            names.append(self.tax_line_id.name)
        return ', '.join(names)

    def om_print_analytic_labels(self):
        """ The analytic accounts of a line, as the lines of the analytic column """
        self.ensure_one()
        result = []
        for key, percentage in (self.analytic_distribution or {}).items():
            accounts = self.env['account.analytic.account'].browse(
                int(account_id) for account_id in key.split(',')).exists()
            if accounts:
                names = ['%s - %s' % (account.name, account.partner_id.name) if account.partner_id else account.name
                         for account in accounts]
                result.append('%s: %s%%' % (', '.join(names), percentage))
        return result
