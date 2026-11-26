from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

BS = 'om.dynamic.report.balance.sheet'
TB = 'om.dynamic.report.trial.balance'
CAPITAL = 'Capital and Reserves'
PREVIOUS = 'Previous Years Unallocated Earnings'
CURRENT = 'Current Year Unallocated Earnings'


@tagged('post_install', '-at_install')
class TestUnallocatedEarnings(AccountTestInvoicingCommon):
    """ The earnings of the Balance Sheet split by fiscal year, as the PDF report has them
    (accounting_pdf_reports, test_unallocated_earnings), in the columns of the Dynamic Reports too. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.retained_earnings = cls.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })

    def _sale(self, date, amount, partner=None):
        self.init_invoice('out_invoice', partner=partner, amounts=[amount], invoice_date=date, taxes=[], post=True)

    def _allocate(self, date, amount):
        """ The result of the year to the reserves, as the year-end closing does """
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': date,
            'line_ids': [
                (0, 0, {'name': 'allocation', 'balance': amount,
                        'account_id': self.env.company.get_unaffected_earnings_account().id}),
                (0, 0, {'name': 'allocation', 'balance': -amount, 'account_id': self.retained_earnings.id}),
            ],
        }).action_post()

    def _report(self, **options):
        """ :return: the report, {line name: (values, parent name)} of its lines, unfolded """
        report = self.env[BS].om_get_report({'date_preset': 'custom', **options})
        lines = {}

        def walk(parent_lines, parent=None):
            for line in parent_lines:
                lines[line['name']] = (line['values'], parent)
                if line['has_children']:
                    walk(self.env[BS].om_get_children(report['options'], line['id'], 0)['lines'], line['name'])
        walk(report['lines'])
        return report, lines

    def _pdf(self, date_to):
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        context = {'date_from': False, 'date_to': date_to, 'state': 'posted', 'strict_range': False,
                   'company_id': self.env.company.id}
        return {line['name']: line['balance'] for line in
                self.env['report.accounting_pdf_reports.report_financial'].with_context(**context).get_account_lines({
                    'account_report_id': (report.id, report.name), 'used_context': context,
                    'enable_filter': False, 'debit_credit': False})}

    def test_the_earnings_split_by_fiscal_year(self):
        """ The same amounts as the PDF report, and no line for the unaffected earnings account """
        self._sale('2024-06-01', 400.0)
        self._allocate('2024-12-31', 400.0)
        self._sale('2025-06-01', 1000.0)
        self._sale('2026-03-01', 300.0)

        _report, lines = self._report(date_to='2026-06-30')
        pdf = self._pdf('2026-06-30')
        for name, amount in ((CAPITAL, 400.0), (PREVIOUS, 1000.0), (CURRENT, 300.0), ('Equity', 1700.0)):
            self.assertAlmostEqual(lines[name][0]['balance'], amount, 2, name)
            self.assertAlmostEqual(pdf[name], amount, 2, name)
        self.assertAlmostEqual(lines['Assets'][0]['balance'], lines['Liabilities and Equity'][0]['balance'], 2)
        unaffected = self.env.company.get_unaffected_earnings_account()
        self.assertFalse([name for name in lines if name.startswith(unaffected.code)])

    def test_the_trial_balance_agrees(self):
        """ The previous years' earnings are the Undistributed Profits/Losses of the Trial Balance """
        self._sale('2024-06-01', 400.0)
        self._allocate('2024-12-31', 400.0)
        self._sale('2025-06-01', 1000.0)
        self._sale('2026-03-01', 300.0)

        trial_balance = self.env[TB].om_get_report({
            'date_preset': 'custom', 'date_from': '2026-01-01', 'date_to': '2026-06-30'})
        undistributed = next(line for line in trial_balance['lines'] if line['id'] == 'undistributed')
        _report, lines = self._report(date_to='2026-06-30')
        self.assertAlmostEqual(lines[PREVIOUS][0]['balance'], -undistributed['values']['init_balance'], 2)

    def test_compared_with_the_previous_year(self):
        """ Each period has the earnings of its own fiscal year """
        self._sale('2025-06-01', 1000.0)
        self._allocate('2025-12-31', 1000.0)
        self._sale('2026-03-01', 300.0)

        _report, lines = self._report(date_to='2026-06-30', compare='previous_year', compare_periods=1)
        self.assertAlmostEqual(lines[CURRENT][0]['balance'], 300.0, 2)
        self.assertAlmostEqual(lines[CURRENT][0]['balance_1'], 1000.0, 2, 'at 30/06/2025, the year not closed')
        self.assertAlmostEqual(lines[CAPITAL][0]['balance_1'], 0.0, 2)

    def test_in_another_currency(self):
        """ The earnings at the rates they were earned at, the reserves at the closing rate, and the
        translation adjustment in the equity """
        eur = self.setup_other_currency('EUR', rates=[('2025-01-01', 0.5), ('2026-06-30', 1.0)])
        self._sale('2025-06-01', 1000.0)
        self._allocate('2025-12-31', 1000.0)
        self._sale('2026-03-01', 300.0)

        report, lines = self._report(date_to='2026-12-31', presentation_currency=str(eur.id))
        self.assertEqual(report['currency_id'], eur.id)
        self.assertAlmostEqual(lines[CURRENT][0]['balance'], 300.0 * 0.5, 2, 'earned in March, at 0.5')
        self.assertAlmostEqual(lines[PREVIOUS][0]['balance'], 0.0, 2, 'earned and allocated in 2025, at 0.5')
        self.assertAlmostEqual(lines[CAPITAL][0]['balance'], 1000.0, 2, 'at the closing rate')
        self.assertEqual(lines['Currency translation adjustment'][1], 'Equity')
        self.assertAlmostEqual(lines['Assets'][0]['balance'], lines['Liabilities and Equity'][0]['balance'], 2)

    def test_in_analytic_columns(self):
        self.env.user.group_ids |= self.env.ref('analytic.group_analytic_accounting')
        plan = self.env['account.analytic.plan'].create({'name': 'Regions'})
        north = self.env['account.analytic.account'].create({'name': 'North', 'plan_id': plan.id})
        for date, amount in (('2025-06-01', 1000.0), ('2026-03-01', 300.0)):
            invoice = self.init_invoice('out_invoice', amounts=[amount], invoice_date=date, taxes=[])
            invoice.invoice_line_ids.analytic_distribution = {str(north.id): 100}
            invoice.action_post()
        self._allocate('2025-12-31', 1000.0)

        _report, lines = self._report(date_to='2026-06-30', analytic_column_ids=[north.id])
        key = 'an_a%s' % north.id
        # the allocation has no analytic: the column keeps the earnings of 2025 as not allocated
        self.assertAlmostEqual(lines[PREVIOUS][0][key], 1000.0, 2)
        self.assertAlmostEqual(lines[CURRENT][0][key], 300.0, 2)
        self.assertAlmostEqual(lines[PREVIOUS][0]['balance'], 0.0, 2)

    def test_in_horizontal_group_columns(self):
        self._sale('2025-06-01', 1000.0, partner=self.partner_a)
        self._allocate('2025-12-31', 1000.0)
        self._sale('2026-03-01', 300.0, partner=self.partner_b)
        group = self.env['om.report.horizontal.group'].create({
            'name': 'Partners',
            'rule_ids': [(0, 0, {'field_id': self.env['ir.model.fields']._get('account.move.line', 'partner_id').id})],
        })

        report, lines = self._report(date_to='2026-06-30', horizontal_group=str(group.id))
        by_label = {column['label']: column['key'] for column in report['columns']}
        a, b = by_label[self.partner_a.display_name], by_label[self.partner_b.display_name]
        self.assertAlmostEqual(lines[PREVIOUS][0][a], 1000.0, 2, 'the sale of 2025: the allocation has no partner')
        self.assertAlmostEqual(lines[CURRENT][0][a], 0.0, 2)
        self.assertAlmostEqual(lines[CURRENT][0][b], 300.0, 2)

    def test_horizontal_group_columns_from_the_earnings_accounts(self):
        """ The columns of a horizontal group take their values from the earnings accounts too: a product is
        only on the income lines, never on the receivable """
        self.init_invoice('out_invoice', products=[self.product_a], invoice_date='2025-06-01', taxes=[], post=True)
        self.init_invoice('out_invoice', products=[self.product_b], invoice_date='2026-03-01', taxes=[], post=True)
        group = self.env['om.report.horizontal.group'].create({
            'name': 'Products',
            'rule_ids': [(0, 0, {'field_id': self.env['ir.model.fields']._get('account.move.line', 'product_id').id})],
        })

        report, lines = self._report(date_to='2026-06-30', horizontal_group=str(group.id))
        by_label = {column['label']: column['key'] for column in report['columns']}
        self.assertIn(self.product_a.display_name, by_label, 'a column for each product')
        a, b = by_label[self.product_a.display_name], by_label[self.product_b.display_name]
        self.assertAlmostEqual(lines[PREVIOUS][0][a], self.product_a.lst_price, 2, 'sold in 2025, not allocated')
        self.assertAlmostEqual(lines[CURRENT][0][b], self.product_b.lst_price, 2, 'sold in 2026')
