from odoo import models

from odoo.addons.account.models.chart_template import template

MODULE = 'om_account_bank_statement_import'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template(model='account.statement.import.map', demo=True)
    def _get_demo_data_om_statement_import_map(self, template_code):
        """ The map of the CSV export of a bank, see static/demo/demo_bank_statement.csv """
        company = self.env.company
        if not self.ref('bank', raise_if_not_found=False):
            return {}
        return {
            '%s.%s_demo_statement_import_map' % (MODULE, company.id): {
                'name': 'Demo Bank - CSV export',
                'company_id': company.id,
                'note': 'The columns of the CSV statements of the demo bank, e.g. the file '
                        '/om_account_bank_statement_import/static/demo/demo_bank_statement.csv',
                'file_encoding': 'utf-8',
                'delimiter': ',',
                'quotechar': '"',
                'decimal_separator': '.',
                'thousands_separator': False,
                'date_format': '%Y-%m-%d',
                'has_header': True,
                'debit_positive': True,
                'column_date': 'Date',
                'column_label': 'Description',
                'column_amount': False,
                'column_debit': 'Debit',
                'column_credit': 'Credit',
                'column_ref': 'Reference',
                'column_partner': 'Counterparty',
                'column_account_number': 'Counterparty Account',
                'column_unique_id': 'Transaction ID',
            },
        }

    @template(model='account.journal', demo=True)
    def _get_demo_data_om_statement_import_journal(self, template_code):
        """ The bank journal reads its CSV statements with the demo map """
        company = self.env.company
        if not self.ref('bank', raise_if_not_found=False):
            return {}
        return {
            'bank': {
                'statement_import_map_id': '%s.%s_demo_statement_import_map' % (MODULE, company.id),
            },
        }
