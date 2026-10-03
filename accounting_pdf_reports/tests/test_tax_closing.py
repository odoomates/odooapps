from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxClosing(AccountTestInvoicingCommon):
    """ The periods of the tax report and the closing of a tax period """

    def _post(self, move_type, tax, amount):
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner_a.id,
            'invoice_date': '2025-03-10', 'date': '2025-03-10',
            'invoice_line_ids': [Command.create({'name': 'test line', 'price_unit': amount,
                                                 'tax_ids': [Command.set(tax.ids)]})],
        })
        move.action_post()
        return move

    def test_period_shortcuts(self):
        wizard = Form(self.env['account.tax.report.wizard'])
        today = fields.Date.context_today(self.env.user)
        wizard.period = 'last_quarter'
        first = today.replace(day=1, month=(today.month - 1) // 3 * 3 + 1)
        last_quarter_start = date(first.year - 1, 10, 1) if first.month == 1 else first.replace(month=first.month - 3)
        self.assertEqual(wizard.date_from, last_quarter_start)
        self.assertEqual(wizard.date_to, first - timedelta(days=1))
        wizard.period = 'this_year'
        dates = self.env.company.compute_fiscalyear_dates(today)
        self.assertEqual((wizard.date_from, wizard.date_to), (dates['date_from'], dates['date_to']))

    def test_tax_closing_entry(self):
        """ The tax due on the period leaves the tax accounts: 150 collected less 60 paid, 90 owed. """
        self._post('out_invoice', self.tax_sale_a, 1000.0)
        self._post('in_invoice', self.tax_purchase_a, 400.0)
        payable = self.env['account.account'].create({
            'code': 'TAXPAY', 'name': 'Tax Payable', 'account_type': 'liability_current'})
        receivable = self.env['account.account'].create({
            'code': 'TAXREC', 'name': 'Tax Receivable', 'account_type': 'asset_current'})
        values = {'date_from': '2025-03-01', 'date_to': '2025-03-31',
                  'journal_id': self.company_data['default_journal_misc'].id,
                  'payable_account_id': payable.id, 'receivable_account_id': receivable.id}
        closing = self.env['account.tax.closing.wizard'].create(values)
        move = self.env['account.move'].browse(closing.action_close()['res_id'])
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.date, date(2025, 3, 31))
        self.assertAlmostEqual(sum(move.line_ids.mapped('balance')), 0.0)
        self.assertEqual(move.line_ids.filtered(lambda line: line.account_id == payable).balance, -90.0)
        self.assertFalse(move.line_ids.filtered(lambda line: line.account_id == receivable))
        self.assertEqual(self.env.company.om_tax_payable_account_id, payable, 'proposed again next time')
        with self.assertRaises(UserError):
            self.env['account.tax.closing.wizard'].create(values).action_close()
        with self.assertRaises(UserError):
            self.env['account.tax.closing.wizard'].create(dict(values, date_from='2024-01-01', date_to='2024-01-31'))\
                .action_close()
