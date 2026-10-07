from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAgedPartnerBalance(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()

    def _aged_lines(self, env, date='2025-12-31'):
        wizard = env['account.aged.trial.balance'].create({'date_from': date})
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        values = env['report.accounting_pdf_reports.report_agedpartnerbalance'].with_context(
            active_model=wizard._name, active_id=wizard.id)._get_report_values(None, data)
        return {line['partner_id']: line for line in values['get_partner_lines']}

    def _aged_balance(self, env, date='2025-12-31'):
        return {partner_id: line['total'] for partner_id, line in self._aged_lines(env, date).items()}

    def _pay(self, invoice, amount, date):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': date, 'amount': amount, 'payment_difference_handling': 'open'})._create_payments()

    def test_aged_balance_of_the_active_company(self):
        company_2 = self.company_data_2['company']
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_b, amounts=[250.0], taxes=[],
                          invoice_date='2025-06-01', post=True, company=company_2)
        user = self.env.user
        user.company_ids |= company_2
        self.assertNotEqual(user.company_id, company_2)

        # the report of the company selected in the switcher, not the default company of the user
        env_company_2 = self.env(context=dict(self.env.context, allowed_company_ids=[company_2.id, user.company_id.id]))
        self.assertEqual(self._aged_balance(env_company_2), {self.partner_b.id: 250.0})
        self.assertEqual(self._aged_balance(self.env), {self.partner_a.id: 100.0})

    def test_aged_balance_as_of_a_date(self):
        """ An item counts with what was paid until the date of the report, not after it """
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[1000.0], taxes=[],
                                    invoice_date='2025-06-01', post=True)
        self._pay(invoice, 400.0, '2025-07-01')
        self._pay(invoice, 600.0, '2026-01-15')
        self.assertTrue(invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable').reconciled)

        self.assertEqual(self._aged_balance(self.env, '2025-06-15'), {self.partner_a.id: 1000.0})
        self.assertEqual(self._aged_balance(self.env, '2025-12-31'), {self.partner_a.id: 600.0})
        self.assertEqual(self._aged_balance(self.env, '2026-02-01'), {})

    def test_aged_balance_periods(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-12-20', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[200.0], taxes=[],
                          invoice_date='2025-11-15', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[300.0], taxes=[],
                          invoice_date='2025-01-10', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[50.0], taxes=[],
                          invoice_date='2025-12-31', post=True)

        line = self._aged_lines(self.env)[self.partner_a.id]
        self.assertEqual(line['direction'], 50.0)  # not due
        self.assertEqual(line['4'], 100.0)  # 1-30 days
        self.assertEqual(line['3'], 200.0)  # 31-60 days
        self.assertEqual(line['0'], 300.0)  # more than 120 days
        self.assertEqual(line['total'], 650.0)
