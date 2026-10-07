from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestGeneralLedger(AccountTestInvoicingCommon):

    def _ledger(self, **vals):
        wizard = self.env['account.report.general.ledger'].create(vals)
        wizard_context = dict(active_model=wizard._name, active_id=wizard.id, active_ids=wizard.ids)
        action = wizard.with_context(**wizard_context).check_report()
        context = dict(wizard_context, **(action.get('context') or {}))
        values = self.env['report.' + action['report_name']].with_context(**context)._get_report_values(
            context.get('active_ids'), action['data'])
        return {account['code']: account for account in values['Accounts']}

    def test_running_balance(self):
        for date, amount in (('2025-01-10', 100.0), ('2025-02-05', 200.0), ('2025-02-20', 50.0)):
            self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                              invoice_date=date, post=True)
        receivable = self.partner_a.property_account_receivable_id

        ledger = self._ledger(date_from='2025-02-01', date_to='2025-02-28', initial_balance=True)
        account = ledger[receivable.code]
        self.assertEqual([line['lname'] for line in account['move_lines']][0], 'Initial Balance')
        # each line carries the balance of the account after it, from the initial balance on
        self.assertEqual([line['balance'] for line in account['move_lines']], [100.0, 300.0, 350.0])
        self.assertEqual((account['debit'], account['credit'], account['balance']), (350.0, 0.0, 350.0))

        ledger = self._ledger(date_from='2025-02-01', date_to='2025-02-28', initial_balance=False)
        self.assertEqual([line['balance'] for line in ledger[receivable.code]['move_lines']], [200.0, 250.0])
