from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxGrid(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        country = cls.env.company.account_fiscal_country_id
        cls.report = cls.env['account.report'].create({
            'name': 'Test VAT Return',
            'root_report_id': cls.env.ref('account.generic_tax_report').id,
            'country_id': country.id,
            'column_ids': [Command.create({'name': 'Balance', 'expression_label': 'balance'})],
            'line_ids': [
                Command.create({'name': 'Sales', 'code': 'SALES', 'sequence': 1,
                                'aggregation_formula': 'BASE.balance + TAX.balance'}),
                Command.create({'name': 'Base', 'code': 'BASE', 'sequence': 2, 'tax_tags_formula': '-TGB'}),
                Command.create({'name': 'Tax', 'code': 'TAX', 'sequence': 3, 'tax_tags_formula': '-TGT'}),
                Command.create({'name': 'Tax a third', 'code': 'THIRD', 'sequence': 4, 'expression_ids': [
                    Command.create({'label': 'balance', 'engine': 'aggregation', 'formula': 'TAX.balance / 7',
                                    'subformula': 'round(0)'})]}),
                Command.create({'name': 'To pay over 500', 'code': 'OVER', 'sequence': 5, 'expression_ids': [
                    Command.create({'label': 'balance', 'engine': 'aggregation', 'formula': 'TAX.balance - 500',
                                    'subformula': 'if_above(CUR(0))'})]}),
            ],
        })
        tags = cls.env['account.account.tag']
        base_tag = tags._get_tax_tags('TGB', country.id)
        tax_tag = tags._get_tax_tags('TGT', country.id)
        cls.tax = cls.tax_sale_a.copy({'name': 'Grid VAT 15%'})
        for line in cls.tax.invoice_repartition_line_ids | cls.tax.refund_repartition_line_ids:
            line.tag_ids = base_tag if line.repartition_type == 'base' else tax_tag

    def _post(self, move_type, amount, date='2025-03-10'):
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner_a.id, 'invoice_date': date, 'date': date,
            'invoice_line_ids': [Command.create({'name': 'line', 'price_unit': amount,
                                                 'tax_ids': [Command.set(self.tax.ids)]})],
        })
        move.action_post()
        return move

    def _grid(self, date_from='2025-03-01', date_to='2025-03-31'):
        self.env.flush_all()
        lines = self.env['report.accounting_pdf_reports.report_tax_grid'].get_lines(self.report, {
            'date_from': date_from, 'date_to': date_to, 'target_move': 'posted',
            'used_context': {'company_id': self.env.company.id},
        })
        return {line['code']: line['values'][0]['value'] for line in lines}

    def test_the_grids_add_up_the_tags_of_the_journal_items(self):
        self._post('out_invoice', 1000.0)
        self._post('out_refund', 100.0)
        self._post('out_invoice', 5000.0, date='2025-04-02')
        grid = self._grid()
        # the sales are credits: a grid with a minus prints them as positive, a refund deducted
        self.assertEqual(grid['BASE'], 900.0)
        self.assertEqual(grid['TAX'], 135.0)
        self.assertEqual(grid['SALES'], 1035.0)
        self.assertEqual(grid['THIRD'], 19.0)
        self.assertEqual(grid['OVER'], 0.0)
        self.assertEqual(self._grid('2025-04-01', '2025-04-30')['OVER'], 250.0)

    def test_the_wizard_prints_the_tax_return_of_the_country(self):
        self._post('out_invoice', 1000.0)
        wizard = self.env['account.tax.report.wizard'].create({
            'period': 'custom', 'date_from': '2025-03-01', 'date_to': '2025-03-31',
            'report_kind': 'grid', 'tax_grid_report_id': self.report.id,
        })
        action = wizard.check_report()
        self.assertEqual(action['report_name'], 'accounting_pdf_reports.report_tax_grid')
        html, _format = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_tax_grid', wizard.ids, data=action['data'])
        self.assertIn('Test VAT Return', html.decode())
        self.assertIn('To pay over 500', html.decode())
