from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAgedPartnerBalance(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()

    def _aged_balance(self, env):
        wizard = env['account.aged.trial.balance'].create({'date_from': '2025-12-31'})
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        values = env['report.accounting_pdf_reports.report_agedpartnerbalance'].with_context(
            active_model=wizard._name, active_id=wizard.id)._get_report_values(None, data)
        return {line['partner_id']: line['total'] for line in values['get_partner_lines']}

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
