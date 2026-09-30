from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestReportTemplates(AccountTestInvoicingCommon):
    """ Every report prints, in the style of the module. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.init_invoice('out_invoice', partner=cls.partner_a, amounts=[1000.0],
                                       invoice_date='2026-03-01', post=True)

    def _render(self, model, **values):
        wizard = self.env[model].create(values)
        action = wizard.with_context(active_model=model, active_ids=wizard.ids, active_id=wizard.id).check_report()
        self.assertEqual(action['type'], 'ir.actions.report')
        html, __ = self.env['ir.actions.report'].with_context(
            active_model=model, active_ids=wizard.ids, active_id=wizard.id,
        )._render_qweb_html(action['report_name'], wizard.ids, data=action['data'])
        return html.decode()

    def test_every_report_prints_in_the_module_style(self):
        balance_sheet = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        profit_loss = self.env.ref('accounting_pdf_reports.account_financial_report_profitandloss0')
        period = {'date_from': '2026-01-01', 'date_to': '2026-12-31'}
        reports = [
            ('account.report.general.ledger', period),
            ('account.report.partner.ledger', period),
            ('account.balance.report', period),
            ('account.tax.report.wizard', period),
            ('account.aged.trial.balance', {'date_from': '2026-12-31'}),
            ('account.print.journal', period),
            ('accounting.report', dict(period, account_report_id=balance_sheet.id)),
            ('accounting.report', dict(period, account_report_id=profit_loss.id)),
            ('accounting.report', dict(period, account_report_id=profit_loss.id, enable_filter=True,
                                       date_from_cmp='2025-01-01', date_to_cmp='2025-12-31')),
            ('accounting.report', dict(period, account_report_id=profit_loss.id, debit_credit=True)),
            ('account.cash.flow.report', period),
            ('account.cash.flow.report', dict(period, display_detail='accounts')),
        ]
        for model, values in reports:
            with self.subTest(model=model, values=values):
                html = self._render(model, **values)
                self.assertIn('o_om_report', html)

    def test_the_journal_entry_prints_on_the_letterhead(self):
        html, __ = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_journal_entries', self.invoice.ids)
        self.assertIn(self.invoice.name, html.decode())
        self.assertFalse(self.env.ref('accounting_pdf_reports.action_report_journal_entries').paperformat_id)
        self.assertEqual(self.env.ref('accounting_pdf_reports.action_report_general_ledger').paperformat_id,
                         self.env.ref('accounting_pdf_reports.paperformat_om_report'))
