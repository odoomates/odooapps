from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPartnerLedger(AccountTestInvoicingCommon):

    def _ledger(self, **vals):
        wizard = self.env['account.report.partner.ledger'].create(vals)
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        return self.env['report.accounting_pdf_reports.report_partnerledger']._get_report_values(None, data)

    def test_partner_ledger(self):
        for partner, amounts in ((self.partner_a, [100.0, 40.0]), (self.partner_b, [250.0])):
            for date, amount in zip(('2025-06-01', '2025-07-01'), amounts):
                self.init_invoice('out_invoice', partner=partner, amounts=[amount], taxes=[],
                                  invoice_date=date, post=True)
        self.init_invoice('out_refund', partner=self.partner_a, amounts=[30.0], taxes=[],
                          invoice_date='2025-08-01', post=True)

        values = self._ledger(result_selection='customer')
        data, docs = values['data'], values['docs']
        self.assertEqual({partner.id for partner in docs}, {self.partner_a.id, self.partner_b.id})

        sum_partner, lines = values['sum_partner'], values['lines']
        self.assertEqual(sum_partner(data, self.partner_a, 'debit'), 140.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'credit'), 30.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'debit - credit'), 110.0)
        self.assertEqual(sum_partner(data, self.partner_b, 'debit - credit'), 250.0)
        self.assertIsNone(sum_partner(data, self.partner_a, 'balance'))

        rows = lines(data, self.partner_a)
        self.assertEqual([row['debit'] - row['credit'] for row in rows], [100.0, 40.0, -30.0])
        self.assertEqual([row['progress'] for row in rows], [100.0, 140.0, 110.0])
        # the payment terms of partner b split its invoice in two installments
        self.assertEqual(sum(row['debit'] - row['credit'] for row in lines(data, self.partner_b)), 250.0)

        # the methods for one partner give the same
        report = self.env['report.accounting_pdf_reports.report_partnerledger']
        self.assertEqual(report._sum_partner(data, self.partner_a, 'debit - credit'), 110.0)
        self.assertEqual([row['progress'] for row in report._lines(data, self.partner_a)], [100.0, 140.0, 110.0])

    def test_partner_ledger_of_selected_partners(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        partner_c = self.env['res.partner'].create({'name': 'Partner without entries'})

        values = self._ledger(result_selection='customer', partner_ids=[(6, 0, partner_c.ids)])
        self.assertEqual(values['docs'], [partner_c])
        self.assertEqual(values['sum_partner'](values['data'], partner_c, 'debit - credit'), 0.0)
        self.assertEqual(values['lines'](values['data'], partner_c), [])
