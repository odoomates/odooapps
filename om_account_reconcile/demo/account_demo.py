from odoo import Command, models

from odoo.addons.account.models.chart_template import template

MODULE = 'om_account_reconcile'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_reconcile_demo_account(self, xml_id, account_type, names):
        """ The account of the generic chart, else the first account of the type named like one of the names,
        else any account of the type """
        company = self.env.company
        Account = self.env['account.account'].with_company(company)
        data = self.env['ir.model.data'].sudo().search([
            ('name', '=', '%d_%s' % (company.id, xml_id)), ('model', '=', 'account.account'),
        ], limit=1)
        account = Account.browse(data.res_id).exists()
        for name in names:
            account = account or Account.search([
                *Account._check_company_domain(company),
                ('account_type', '=', account_type),
                ('name', 'ilike', name),
            ], limit=1)
        return account or self._get_demo_account(xml_id, account_type, company)

    @template(model='account.reconcile.model', demo=True)
    def _get_demo_data_om_reconcile_model(self, template_code):
        """ A write-off, a partner mapping and a matching rule working on the demo transactions of the
        accounting module (the bank fees write-off is in its demo already) """
        company = self.env.company
        rent_account = self._om_reconcile_demo_account('expense_rent', 'expense', ('Office Rent', 'Rent'))
        discount_account = self._om_reconcile_demo_account(
            'cash_discount_loss', 'expense', ('Cash Discount', 'Discount', 'Bank Fees'))
        if not rent_account or not discount_account:
            return {}
        return {
            # one click on the "Office rent" transactions
            '%s.%s_demo_reco_office_rent' % (MODULE, company.id): {
                'name': 'Office Rent',
                'sequence': 20,
                'match_label': 'contains',
                'match_label_param': 'rent',
                'match_amount': 'lower',
                'match_amount_max': 5000.0,
                'line_ids': [
                    Command.create({
                        'label': 'Office rent',
                        'account_id': rent_account.id,
                        'amount_type': 'percentage',
                        'amount_string': '100',
                    }),
                ],
            },
            # OpenWood writes "invoice #<number>" in its transfers, without its name
            '%s.%s_demo_reco_partner_openwood' % (MODULE, company.id): {
                'name': 'OpenWood: "invoice #" transfers',
                'sequence': 5,
                'match_label': 'contains',
                'match_label_param': 'invoice #',
                'line_ids': [
                    Command.create({
                        'partner_id': 'base.res_partner_5',
                        'amount_type': 'percentage',
                        'amount_string': '100',
                    }),
                ],
            },
            # customers paying a little less than the invoice, e.g. bank charges on their side
            '%s.%s_demo_reco_matching_tolerance' % (MODULE, company.id): {
                'name': 'Invoices Paid within 2%',
                'sequence': 10,
                'rule_type': 'matching_rule',
                'match_amount': 'lower',
                'match_amount_max': 10000.0,
                'payment_tolerance': 2.0,
                'payment_tolerance_type': 'percentage',
                'matching_order': 'old_first',
                'line_ids': [
                    Command.create({
                        'label': 'Payment difference',
                        'account_id': discount_account.id,
                        'amount_type': 'percentage',
                        'amount_string': '100',
                    }),
                ],
            },
        }
