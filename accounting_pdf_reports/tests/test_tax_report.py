from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxReport(AccountTestInvoicingCommon):

    def _post(self, move_type, tax, amount):
        # the accounting date set as well: the test helpers leave the date of a refund to the form
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner_a.id,
            'invoice_date': '2025-03-10', 'date': '2025-03-10',
            'invoice_line_ids': [Command.create({'name': 'test line', 'price_unit': amount,
                                                 'tax_ids': [Command.set(tax.ids)]})],
        })
        move.action_post()
        return move

    def _tax_lines(self):
        # read with SQL, like the report: it flushes in _get_report_values
        self.env.flush_all()
        lines = self.env['report.accounting_pdf_reports.report_tax'].get_lines({
            'date_from': '2025-01-01', 'date_to': '2025-12-31', 'target_move': 'posted',
            'used_context': {'company_id': self.env.company.id},
        })
        return {
            group: {line['name']: (line['net'], line['tax']) for line in group_lines}
            for group, group_lines in lines.items()
        }

    def test_refunds_are_deducted_and_both_sides_are_positive(self):
        sale_tax, purchase_tax = self.tax_sale_a, self.tax_purchase_a
        for move_type, tax, amount in (
            ('out_invoice', sale_tax, 1000.0),
            ('out_refund', sale_tax, 100.0),
            ('in_invoice', purchase_tax, 400.0),
            ('in_refund', purchase_tax, 40.0),
        ):
            self._post(move_type, tax, amount)

        lines = self._tax_lines()
        # the sales are credits and the purchases debits: both print as positive figures,
        # a refund is deducted from its side
        self.assertEqual(lines['sale'][sale_tax.name], (900.0, 135.0))
        self.assertEqual(lines['purchase'][purchase_tax.name], (360.0, 54.0))

    def test_a_period_of_refunds_stays_negative(self):
        self._post('out_refund', self.tax_sale_a, 100.0)
        self.assertEqual(self._tax_lines()['sale'][self.tax_sale_a.name], (-100.0, -15.0))
