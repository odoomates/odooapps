from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

TB = 'om.dynamic.report.trial.balance'
GL = 'om.dynamic.report.general.ledger'
PL = 'om.dynamic.report.partner.ledger'
AN = 'om.dynamic.report.analytic'
BS = 'om.dynamic.report.balance.sheet'
PNL = 'om.dynamic.report.profit.loss'
AR = 'om.dynamic.report.aged.receivable'
AP = 'om.dynamic.report.aged.payable'
CF = 'om.dynamic.report.cash.flow'
CS = 'om.dynamic.report.customer.statement'
VS = 'om.dynamic.report.vendor.statement'
ES = 'om.dynamic.report.executive.summary'
BR = 'om.dynamic.report.bank.reconciliation'
TX = 'om.dynamic.report.tax'
JA = 'om.dynamic.report.journal.audit'
BB = 'om.dynamic.report.bank.book'
CB = 'om.dynamic.report.cash.book'
DB = 'om.dynamic.report.day.book'
PERIOD = {'date_preset': 'custom', 'date_from': '2026-01-01', 'date_to': '2026-12-31'}


@tagged('post_install', '-at_install')
class TestDynamicReports(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('account.group_account_readonly')
        # last year: an invoice, so that the year starts with a receivable and an undistributed profit
        cls.old_invoice = cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2025-06-01',
                                           amounts=[1000.0], post=True)
        cls.invoice = cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2026-03-10',
                                       amounts=[400.0], post=True)
        cls.bill = cls.init_invoice('in_invoice', partner=cls.partner_b, invoice_date='2026-04-02',
                                    amounts=[250.0], post=True)
        cls.draft = cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2026-05-05',
                                     amounts=[90.0])
        cls.receivable = cls.company_data['default_account_receivable']
        cls.revenue = cls.company_data['default_account_revenue']

    def report(self, model, **options):
        return self.env[model].om_get_report({**PERIOD, **options})

    def line(self, report, name_start):
        return next(line for line in report['lines'] if line['name'].startswith(name_start))

    def children(self, model, report, line, offset=0):
        return self.env[model].om_get_children(report['options'], line['id'], offset)

    # ------------------------------------------------------------------
    # Trial Balance
    # ------------------------------------------------------------------

    def test_trial_balance_matches_the_pdf_report(self):
        report = self.report(TB)
        base = self.env['report.accounting_pdf_reports.report_trialbalance'].with_context(
            date_from='2026-01-01', date_to='2026-12-31', state='posted', strict_range=True,
            company_id=self.env.company.id)._get_accounts(self.env['account.account'].search([]), 'movement')
        expected = {row['code']: row for row in base if row['code']}
        lines = {line['name'].split(' ')[0]: line for line in report['lines'] if line['id'].startswith('account-')}
        self.assertEqual(set(lines), set(expected))
        for code, row in expected.items():
            values = lines[code]['values']
            self.assertAlmostEqual(values['init_balance'], row['initial_balance'], 2, code)
            self.assertAlmostEqual(values['debit'], row['debit'], 2, code)
            self.assertAlmostEqual(values['credit'], row['credit'], 2, code)
            self.assertAlmostEqual(values['end_balance'], row['balance'], 2, code)

    def test_trial_balance_balances(self):
        total = self.report(TB)['total']['values']
        for left, right in (('init_debit', 'init_credit'), ('debit', 'credit'), ('end_debit', 'end_credit')):
            self.assertAlmostEqual(total[left], total[right], 2, left)

    def test_trial_balance_initial_balance_and_undistributed(self):
        report = self.report(TB)
        receivable = self.line(report, self.receivable.code)['values']
        self.assertAlmostEqual(receivable['init_balance'], self.old_invoice.amount_total, 2)
        self.assertAlmostEqual(receivable['init_debit'], self.old_invoice.amount_total, 2)
        # the revenue of last year is not on the revenue account any more, but in the undistributed result
        revenue = self.line(report, self.revenue.code)['values']
        self.assertAlmostEqual(revenue['init_balance'], 0.0, 2)
        undistributed = next(line for line in report['lines'] if line['id'] == 'undistributed')['values']
        self.assertAlmostEqual(undistributed['init_balance'], -1000.0, 2)

    def test_trial_balance_draft_entries(self):
        posted = self.line(self.report(TB), self.receivable.code)['values']['debit']
        everything = self.line(self.report(TB, target_move='all'), self.receivable.code)['values']['debit']
        self.assertAlmostEqual(everything - posted, self.draft.amount_total, 2)

    def test_trial_balance_grouped_by_type(self):
        report = self.report(TB, hierarchy='type')
        self.assertTrue(all(line['kind'] == 'group' for line in report['lines'] if line['id'] != 'undistributed'))
        assets = next(line for line in report['lines'] if line['id'] == 'group-asset')
        types = self.children(TB, report, assets)['lines']
        receivable_type = next(line for line in types if line['id'] == 'group-asset|type-asset_receivable')
        accounts = self.children(TB, report, receivable_type)['lines']
        self.assertIn(self.receivable.id, [int(line['id'].rsplit('-', 1)[1]) for line in accounts])
        self.assertAlmostEqual(sum(line['values']['end_balance'] for line in accounts),
                               receivable_type['values']['end_balance'], 2)

    def test_trial_balance_comparison(self):
        report = self.report(TB, compare='previous_year')
        keys = [column['key'] for column in report['columns']]
        self.assertEqual(len(keys), 18)
        self.assertIn('end_debit_1', keys)
        groups = list(dict.fromkeys(column['group'] for column in report['columns']))
        self.assertEqual(groups, ['Balance at 01/01/2026', '01/01/2026 - 12/31/2026', 'Balance at 12/31/2026',
                                  'Balance at 01/01/2025', '01/01/2025 - 12/31/2025', 'Balance at 12/31/2025'])
        last_year = self.report(TB, date_from='2025-01-01', date_to='2025-12-31')
        compared = {line['id']: line['values'] for line in report['lines']}
        for line in last_year['lines']:
            for key in ('init_balance', 'debit', 'credit', 'end_balance'):
                self.assertAlmostEqual(compared[line['id']][key + '_1'], line['values'][key], 2, line['name'])
        # the receivable of last year closes what this year opens with
        receivable = compared['account-%s' % self.receivable.id]
        self.assertAlmostEqual(receivable['end_balance_1'], receivable['init_balance'], 2)
        self.assertAlmostEqual(report['total']['values']['debit_1'], report['total']['values']['credit_1'], 2)

    def test_trial_balance_parent_and_code_hierarchy(self):
        parent = self.env['account.account'].create({
            'code': '120000', 'name': 'Receivables', 'account_type': 'asset_receivable', 'reconcile': True})
        self.receivable.parent_id = parent
        report = self.report(TB, hierarchy='parent')
        group = next(line for line in report['lines'] if line['id'] == 'parent-%s' % parent.id)
        self.assertEqual(group['kind'], 'group')
        children = self.children(TB, report, group)['lines']
        self.assertEqual([line['id'] for line in children],
                         ['parent-%s|account-%s' % (parent.id, self.receivable.id)])
        self.assertAlmostEqual(group['values']['end_balance'], children[0]['values']['end_balance'], 2)
        flat_total = self.report(TB)['total']['values']
        self.assertAlmostEqual(report['total']['values']['end_debit'], flat_total['end_debit'], 2)

        by_code = self.report(TB, hierarchy='code')
        top = {line['id']: line for line in by_code['lines']}
        prefix = self.receivable.code[:1]
        self.assertIn('code-%s' % prefix, top)
        second = self.children(TB, by_code, top['code-%s' % prefix])['lines']
        self.assertIn('code-%s|code-%s' % (prefix, self.receivable.code[:2]), [line['id'] for line in second])

    def test_general_ledger_grouped_accounts_still_unfold(self):
        report = self.report(GL, hierarchy='code')
        prefix = self.receivable.code
        group = next(line for line in report['lines'] if line['id'] == 'code-%s' % prefix[:1])
        level_two = next(line for line in self.children(GL, report, group)['lines']
                         if line['id'] == 'code-%s|code-%s' % (prefix[:1], prefix[:2]))
        account = next(line for line in self.children(GL, report, level_two)['lines']
                       if line['id'].endswith('account-%s' % self.receivable.id))
        items = self.children(GL, report, account)['lines']
        self.assertEqual(items[0]['kind'], 'opening')
        self.assertAlmostEqual(items[-1]['values']['balance'], account['values']['balance'], 2)

    def test_trial_balance_drill_and_link(self):
        report = self.report(TB)
        line = self.line(report, self.receivable.code)
        action = self.env[TB].om_open_line(report['options'], line['id'])
        self.assertEqual(action['res_model'], 'account.move.line')
        items = self.env['account.move.line'].search(action['domain'])
        self.assertEqual(set(items.account_id.ids), {self.receivable.id})
        self.assertAlmostEqual(sum(items.mapped('debit')), line['values']['debit'], 2)
        self.assertEqual(line['links'][0]['model'], GL)
        self.assertEqual(line['links'][0]['options']['account_ids'], [self.receivable.id])

    # ------------------------------------------------------------------
    # General Ledger
    # ------------------------------------------------------------------

    def test_general_ledger_matches_the_pdf_report(self):
        report = self.report(GL)
        base = self.env['report.accounting_pdf_reports.report_general_ledger'].with_context(
            date_from='2026-01-01', date_to='2026-12-31', state='posted', strict_range=True,
            company_id=self.env.company.id)._get_account_move_entry(
            self.env['account.account'].search([]), False, False, True, 'sort_date', 'movement')
        expected = {row['code']: row for row in base if row['code']}
        lines = {line['name'].split(' ')[0]: line for line in report['lines'] if line['id'].startswith('account-')}
        self.assertEqual(set(lines), set(expected))
        for code, row in expected.items():
            for field in ('debit', 'credit', 'balance'):
                self.assertAlmostEqual(lines[code]['values'][field], row[field], 2, '%s %s' % (code, field))

    def test_general_ledger_running_balance(self):
        report = self.report(GL)
        account = self.line(report, self.receivable.code)
        lines = self.children(GL, report, account)['lines']
        self.assertEqual(lines[0]['kind'], 'opening')
        self.assertAlmostEqual(lines[0]['values']['balance'], self.old_invoice.amount_total, 2)
        self.assertEqual(lines[-1]['kind'], 'detail')
        self.assertAlmostEqual(lines[-1]['values']['balance'], account['values']['balance'], 2)
        self.assertEqual(lines[-1]['open']['res_model'], 'account.move')

    def test_general_ledger_pages_keep_the_running_balance(self):
        for day in range(1, 6):
            self.init_invoice('out_invoice', partner=self.partner_a, invoice_date='2026-07-%02d' % day,
                              amounts=[10.0 * day], post=True)
        report = self.report(GL)
        account = self.line(report, self.receivable.code)
        everything = self.children(GL, report, account)['lines']
        with patch.object(type(self.env[GL]), '_report_page_size', 3):
            pages, offset, more = [], 0, True
            while more:
                result = self.children(GL, report, account, offset)
                pages += result['lines']
                offset += len(result['lines'])
                more = result['more']
        self.assertEqual([line['id'] for line in pages], [line['id'] for line in everything])
        self.assertEqual([line['values']['balance'] for line in pages],
                         [line['values']['balance'] for line in everything])

    def test_general_ledger_without_initial_balance(self):
        report = self.report(GL, initial_balance=False)
        account = self.line(report, self.receivable.code)
        lines = self.children(GL, report, account)['lines']
        self.assertEqual(lines[0]['kind'], 'detail')
        self.assertFalse(any(line['id'] == 'undistributed' for line in report['lines']))

    def test_general_ledger_partner_filter(self):
        report = self.report(GL, partner_ids=[self.partner_b.id])
        lines = self.children(GL, report, self.line(report, self.revenue.code)) \
            if any(line['name'].startswith(self.revenue.code) for line in report['lines']) else {'lines': []}
        self.assertFalse([line for line in lines['lines'] if line['kind'] == 'detail'],
                         "partner B only has a bill: nothing on the revenue account")

    # ------------------------------------------------------------------
    # Partner Ledger
    # ------------------------------------------------------------------

    def test_partner_ledger(self):
        report = self.report(PL)
        partner_a = next(line for line in report['lines'] if line['id'] == 'partner-%s' % self.partner_a.id)
        partner_b = next(line for line in report['lines'] if line['id'] == 'partner-%s' % self.partner_b.id)
        self.assertAlmostEqual(partner_a['values']['balance'],
                               self.old_invoice.amount_total + self.invoice.amount_total, 2)
        self.assertAlmostEqual(partner_b['values']['balance'], -self.bill.amount_total, 2)
        lines = self.children(PL, report, partner_a)['lines']
        self.assertEqual(lines[0]['kind'], 'opening')
        self.assertTrue(lines[-1]['values']['date_maturity'])

        receivable_only = self.report(PL, result_selection='customer')
        self.assertNotIn('partner-%s' % self.partner_b.id, [line['id'] for line in receivable_only['lines']])
        credit_only = self.report(PL, balance_filter='credit')
        self.assertEqual([line['id'] for line in credit_only['lines']], ['partner-%s' % self.partner_b.id])

    def test_partner_ledger_reconciled_entries(self):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.invoice.ids).create({'payment_date': '2026-03-20'}
        )._create_payments()
        with_reconciled = self.report(PL, initial_balance=False)
        open_only = self.report(PL, initial_balance=False, reconciled=False)
        line_id = 'partner-%s' % self.partner_a.id
        self.assertIn(line_id, [line['id'] for line in with_reconciled['lines']])
        self.assertNotIn(line_id, [line['id'] for line in open_only['lines']])

    # ------------------------------------------------------------------
    # Balance Sheet and Profit and Loss
    # ------------------------------------------------------------------

    def statement_lines(self, model, report):
        """{line name: line} of every section and account, unfolded."""
        lines = {}

        def walk(parent_lines):
            for line in parent_lines:
                lines[line['name']] = line
                if line['has_children']:
                    walk(self.children(model, report, line)['lines'])
        walk(report['lines'])
        return lines

    def base_statement(self, xmlid, context):
        root = self.env.ref(xmlid)
        data = {'account_report_id': [root.id], 'used_context': {**context, 'state': 'posted',
                'company_id': self.env.company.id}, 'enable_filter': False, 'debit_credit': True}
        # the root is not a line of the dynamic report: its amount is the total, if any
        return {line['name']: line for line in
                self.env['report.accounting_pdf_reports.report_financial'].get_account_lines(data)
                if line['name'] != root.name}

    def test_balance_sheet_matches_the_pdf_report(self):
        report = self.report(BS, date_preset='custom', date_to='2026-12-31')
        self.assertEqual(report['date_mode'], 'as_of')
        self.assertFalse(report['options']['date_from'])
        lines = self.statement_lines(BS, report)
        base = self.base_statement('accounting_pdf_reports.account_financial_report_balancesheet0',
                                   {'date_to': '2026-12-31'})
        for name, row in base.items():
            if row['type'] == 'account' and abs(row['balance']) < 0.005:
                continue
            self.assertIn(name, lines)
            self.assertAlmostEqual(lines[name]['values']['balance'], row['balance'], 2, name)
        assets = lines['Assets']['values']['balance']
        self.assertAlmostEqual(assets, lines['Liabilities and Equity']['values']['balance'], 2)
        self.assertTrue(assets)
        self.assertFalse(report['total'])

    def test_statement_hides_accounts_at_zero_as_the_pdf_report(self):
        """An account whose movements add up to zero is hidden, unless its debit and credit are shown"""
        zero = self.env['account.account'].create({'code': 'ZERO', 'name': 'Zero', 'account_type': 'asset_current'})
        bank = self.company_data['default_journal_bank'].default_account_id
        for date, balance in (('2026-02-01', 100.0), ('2026-02-15', -100.0)):
            self.env['account.move'].create({
                'journal_id': self.company_data['default_journal_misc'].id,
                'date': date,
                'line_ids': [Command.create({'name': 'zero', 'account_id': zero.id, 'balance': balance}),
                             Command.create({'name': 'zero', 'account_id': bank.id, 'balance': -balance})],
            }).action_post()
        root = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        context = {'date_to': '2026-12-31', 'state': 'posted', 'company_id': self.env.company.id}
        for debit_credit in (False, True):
            with self.subTest(debit_credit=debit_credit):
                report = self.report(BS, date_preset='custom', date_to='2026-12-31', debit_credit=debit_credit)
                shown = {name for name, line in self.statement_lines(BS, report).items() if '|account-' in line['id']}
                pdf = {line['name'] for line in self.env['report.accounting_pdf_reports.report_financial']
                       .get_account_lines({'account_report_id': [root.id], 'used_context': context,
                                           'enable_filter': False, 'debit_credit': debit_credit})
                       if line['type'] == 'account'}
                self.assertEqual(shown, pdf)
                self.assertEqual('ZERO Zero' in shown, debit_credit)
        report = self.report(BS, date_preset='custom', date_to='2026-12-31', hide_zero=False)
        self.assertIn('ZERO Zero', self.statement_lines(BS, report))

    def test_profit_and_loss_matches_the_pdf_report(self):
        report = self.report(PNL)
        lines = self.statement_lines(PNL, report)
        base = self.base_statement('accounting_pdf_reports.account_financial_report_profitandloss0',
                                   {'date_from': '2026-01-01', 'date_to': '2026-12-31', 'strict_range': True})
        for name, row in base.items():
            if row['type'] == 'account' and abs(row['balance']) < 0.005:
                continue
            self.assertAlmostEqual(lines[name]['values']['balance'], row['balance'], 2, name)
        self.assertAlmostEqual(report['total']['values']['balance'], 400.0 - 250.0, 2)
        self.assertEqual(report['total']['name'], 'Net Profit')
        # opened afresh, the sections come unfolded
        opened = self.env[PNL].om_get_report(PERIOD, auto_unfold=True)
        self.assertEqual(set(opened['expanded']) & {line['id'] for line in opened['lines']},
                         {line['id'] for line in opened['lines'] if line['has_children']})
        self.assertFalse(report['expanded'])

    def test_profit_and_loss_comparison(self):
        report = self.report(PNL, compare='previous_year')
        keys = [column['key'] for column in report['columns']]
        self.assertEqual(keys, ['balance', 'balance_1', 'variation'])
        self.assertEqual(report['columns'][1]['label'], '01/01/2025 - 12/31/2025')
        total = report['total']['values']
        self.assertAlmostEqual(total['balance_1'], 1000.0, 2)
        self.assertAlmostEqual(total['variation'], (150.0 - 1000.0) / 1000.0 * 100, 2)
        three = self.report(PNL, compare='previous_year', compare_periods=3)
        self.assertEqual([c['key'] for c in three['columns']], ['balance', 'balance_1', 'balance_2', 'balance_3'])

    def test_statement_debit_credit_and_drill(self):
        report = self.report(PNL, debit_credit=True)
        self.assertEqual([c['key'] for c in report['columns']], ['debit', 'credit', 'balance'])
        lines = self.statement_lines(PNL, report)
        account_line = next(line for name, line in lines.items() if name.startswith(self.revenue.code))
        action = self.env[PNL].om_open_line(report['options'], account_line['id'])
        items = self.env['account.move.line'].search(action['domain'])
        self.assertAlmostEqual(sum(items.mapped('credit')) - sum(items.mapped('debit')),
                               account_line['values']['balance'], 2)

    # ------------------------------------------------------------------
    # Aged Receivable and Payable
    # ------------------------------------------------------------------

    def aged(self, model, **options):
        return self.env[model].om_get_report({'date_preset': 'custom', 'date_to': '2026-12-31', **options})

    def test_aged_receivable_matches_the_pdf_report(self):
        for day in ('2026-12-20', '2026-11-15', '2026-10-01', '2026-08-20', '2026-06-01'):
            self.init_invoice('out_invoice', partner=self.partner_b, invoice_date=day, amounts=[100.0], post=True)
        # paid after the date: still open at the date
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=self.invoice.ids).create({'payment_date': '2027-01-15'}
        )._create_payments()
        report = self.aged(AR)
        base, _total, _lines = self.env['report.accounting_pdf_reports.report_agedpartnerbalance'].with_context(
            company_id=self.env.company.id)._get_partner_move_lines(['asset_receivable'], [], '2026-12-31',
                                                                   'posted', 30)
        lines = {line['id']: line['values'] for line in report['lines']}
        self.assertEqual(set(lines), {'partner-%s' % row['partner_id'] for row in base})
        for row in base:
            values = lines['partner-%s' % row['partner_id']]
            self.assertAlmostEqual(values['not_due'], row['direction'], 2)
            for index in range(4):
                self.assertAlmostEqual(values['period_%s' % index], row[str(4 - index)], 2, index)
            self.assertAlmostEqual(values['older'], row['0'], 2)
            self.assertAlmostEqual(values['total'], row['total'], 2)
        partner_a = lines['partner-%s' % self.partner_a.id]
        self.assertAlmostEqual(partner_a['total'], self.old_invoice.amount_total + self.invoice.amount_total, 2)

    def test_aged_details_and_buckets(self):
        report = self.aged(AR, period_length=60, period_count=2)
        keys = [column['key'] for column in report['columns'] if not column['detail_only']]
        self.assertEqual(keys, ['not_due', 'period_0', 'period_1', 'older', 'total'])
        self.assertEqual([c['label'] for c in report['columns'] if c['key'].startswith('period_')], ['1-60', '61-120'])
        partner = next(line for line in report['lines'] if line['id'] == 'partner-%s' % self.partner_a.id)
        details = self.env[AR].om_get_children(report['options'], partner['id'])['lines']
        self.assertEqual(len(details), 2)
        old = next(line for line in details if line['open']['res_id'] == self.old_invoice.id)
        self.assertEqual(old['values']['days'], 578)
        self.assertAlmostEqual(old['values']['older'], self.old_invoice.amount_total, 2)
        action = self.env[AR].om_open_line(report['options'], partner['id'])
        self.assertEqual(set(self.env['account.move.line'].search(action['domain']).move_id.ids),
                         {self.old_invoice.id, self.invoice.id})

    def test_aged_by_invoice_date_and_payable(self):
        invoice = self.init_invoice('out_invoice', partner=self.partner_b, invoice_date='2026-12-01',
                                    amounts=[100.0])
        invoice.invoice_payment_term_id = False
        invoice.invoice_date_due = '2027-02-01'
        invoice.action_post()
        by_due = self.aged(AR, partner_ids=[self.partner_b.id])['lines'][0]['values']
        by_invoice = self.aged(AR, partner_ids=[self.partner_b.id], aging_basis='invoice')['lines'][0]['values']
        self.assertAlmostEqual(by_due['not_due'], invoice.amount_total, 2)
        self.assertAlmostEqual(by_invoice['period_0'], invoice.amount_total, 2)
        payable = self.aged(AP)
        partner_b = next(line for line in payable['lines'] if line['id'] == 'partner-%s' % self.partner_b.id)
        self.assertAlmostEqual(partner_b['values']['total'], self.bill.amount_total, 2)
        self.assertGreater(partner_b['values']['total'], 0)

    # ------------------------------------------------------------------
    # Cash Flow Statement
    # ------------------------------------------------------------------

    def pay(self, move, day):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create({'payment_date': day})._create_payments()

    def test_cash_flow_matches_the_pdf_report(self):
        self.pay(self.invoice, '2026-03-20')
        self.pay(self.bill, '2026-04-10')
        self.pay(self.old_invoice, '2026-02-01')
        # the payments are only cash once the bank statement is matched: post them straight to the bank
        bank = self.company_data['default_journal_bank']
        for move in (self.invoice, self.bill, self.old_invoice):
            for payment in move.matched_payment_ids:
                payment.move_id.line_ids.filtered(
                    lambda l: l.account_id == payment.outstanding_account_id
                ).account_id = bank.default_account_id
        report = self.report(CF)
        lines = self.statement_lines(CF, report)
        base = self.env['report.accounting_pdf_reports.report_cash_flow']._get_cash_flow({
            'company_id': self.env.company.id, 'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'target_move': 'posted', 'journal_ids': []})
        for section in base['sections']:
            self.assertAlmostEqual(lines[section['name']]['values']['balance'], section['total'], 2)
            for line in section['lines']:
                self.assertAlmostEqual(lines[line['name']]['values']['balance'], line['amount'], 2)
        self.assertAlmostEqual(lines['Net change in cash']['values']['balance'], base['net_change'], 2)
        self.assertAlmostEqual(report['total']['values']['balance'], base['closing'], 2)
        self.assertTrue(base['net_change'])
        received = lines['Cash received from customers']['values']['balance']
        self.assertAlmostEqual(received, self.invoice.amount_total + self.old_invoice.amount_total, 2)

    def test_cash_flow_indirect_method(self):
        self.pay(self.invoice, '2026-03-20')
        self.pay(self.old_invoice, '2026-02-01')
        bank = self.company_data['default_journal_bank']
        for move in (self.invoice, self.old_invoice):
            for payment in move.matched_payment_ids:
                payment.move_id.line_ids.filtered(
                    lambda l: l.account_id == payment.outstanding_account_id).account_id = bank.default_account_id
        direct = self.report(CF)
        indirect = self.report(CF, method='indirect')
        lines = self.statement_lines(CF, indirect)
        # both methods explain the same change of the cash
        self.assertAlmostEqual(lines['Net change in cash']['values']['balance'],
                               self.statement_lines(CF, direct)['Net change in cash']['values']['balance'], 2)
        self.assertAlmostEqual(indirect['total']['values']['balance'], direct['total']['values']['balance'], 2)
        sections = sum(lines[name]['values']['balance'] for name in
                       ('Operating Activities', 'Investing Activities', 'Financing Activities') if name in lines)
        self.assertAlmostEqual(sections, lines['Net change in cash']['values']['balance'], 2)
        # the net profit of the period, then what the receivables did with it
        self.assertAlmostEqual(lines['Net profit']['values']['balance'], 400.0 - 250.0, 2)
        receivables = lines['Decrease (increase) in receivables']['values']['balance']
        self.assertAlmostEqual(receivables, self.old_invoice.amount_total, 2)

    def test_cash_flow_indirect_depreciation(self):
        depreciation = self.env['account.account'].create({
            'code': '680000', 'name': 'Depreciation', 'account_type': 'expense_depreciation'})
        accumulated = self.env['account.account'].create({
            'code': '219000', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        move = self.env['account.move'].create({'date': '2026-06-30', 'line_ids': [
            (0, 0, {'account_id': depreciation.id, 'debit': 100.0}),
            (0, 0, {'account_id': accumulated.id, 'credit': 100.0})]})
        move.action_post()
        lines = self.statement_lines(CF, self.report(CF, method='indirect'))
        self.assertAlmostEqual(lines['Depreciation and amortisation (non-cash)']['values']['balance'], 100.0, 2)
        # no cash moved: the fixed assets give back what the depreciation added
        self.assertAlmostEqual(lines['Fixed and non-current assets']['values']['balance'], 0.0, 2)
        self.assertAlmostEqual(lines['Less depreciation (non-cash)']['values']['balance'], -100.0, 2)

    def test_cash_flow_comparison_and_drill(self):
        report = self.report(CF, compare='previous_year')
        self.assertEqual([c['key'] for c in report['columns']], ['balance', 'balance_1', 'variation'])
        self.assertNotIn('debit_credit', [t['key'] for t in report['toggles']])
        for line_id in ('opening', 'net_change'):
            action = self.env[CF].om_open_line(report['options'], line_id)
            self.assertEqual(action['res_model'], 'account.move.line')

    # ------------------------------------------------------------------
    # Executive Summary
    # ------------------------------------------------------------------

    def summary(self, **options):
        report = self.env[ES].om_get_report({**PERIOD, **options}, auto_unfold=True)
        figures = {}
        for children in report['children'].values():
            for line in children['lines']:
                figures[line['id'].rpartition('figure-')[2]] = line
        return report, figures

    def test_executive_summary_agrees_with_the_reports(self):
        report, figures = self.summary()
        self.assertEqual([line['name'] for line in report['lines']],
                         ['Profitability', 'Cash', 'Balance Sheet', 'Ratios'])
        value = lambda key: figures[key]['values']['value']  # noqa: E731
        net_profit = self.report(PNL)['total']['values']['balance']
        self.assertAlmostEqual(value('net_profit'), net_profit, 2)
        self.assertAlmostEqual(value('revenue'), 400.0, 2)
        aged = self.env[AR].om_get_report({'date_preset': 'custom', 'date_to': '2026-12-31'})
        self.assertAlmostEqual(value('receivables'), aged['total']['values']['total'], 2)
        bs = self.statement_lines(BS, self.report(BS, date_preset='custom', date_to='2026-12-31'))
        self.assertAlmostEqual(value('total_assets'), bs['Assets']['values']['balance'], 2)
        self.assertAlmostEqual(value('net_assets'), bs['Equity']['values']['balance'], 2)
        cash = self.report(CF)['total']
        self.assertAlmostEqual(value('cash_closing'), cash['values']['balance'] if cash else 0.0, 2)
        # the ratios, in their own formats
        self.assertEqual(figures['current_ratio']['types']['value'], 'ratio')
        self.assertEqual(figures['dso']['types']['value'], 'days')
        self.assertAlmostEqual(value('net_margin'), net_profit / 400.0 * 100, 2)
        self.assertAlmostEqual(value('dso'), value('receivables') * 365 / 400.0, 2)
        self.assertFalse(figures['current_ratio']['drill'])

    def test_executive_summary_comparison_and_drill(self):
        report, figures = self.summary(compare='previous_year')
        self.assertEqual([c['key'] for c in report['columns']], ['value', 'value_1', 'variation'])
        revenue = figures['revenue']
        self.assertAlmostEqual(revenue['values']['value_1'], 1000.0, 2)
        self.assertAlmostEqual(revenue['values']['variation'], (400.0 - 1000.0) / 1000.0 * 100, 2)
        self.assertNotIn('variation', figures['net_margin']['values'])
        action = self.env[ES].om_open_cell(report['options'], revenue['id'], 'value_1')
        items = self.env['account.move.line'].search(action['domain'])
        self.assertAlmostEqual(-sum(items.mapped('balance')), 1000.0, 2)
        received = self.env[ES].om_open_cell(report['options'], figures['receivables']['id'], 'value')
        self.assertAlmostEqual(sum(self.env['account.move.line'].search(received['domain']).mapped('balance')),
                               figures['receivables']['values']['value'], 2)

    def test_executive_summary_exports(self):
        content, _filename, _mimetype = self.env['om.report.export']._om_render_file(
            {'model': ES, 'format': 'xlsx', 'options': PERIOD, 'expand_all': True})
        self.assertTrue(content)
        export = self.env[ES].om_export_data(PERIOD, expand_all=True)
        dso = next(line for line in export['lines'] if line['id'].endswith('figure-dso'))
        cell = self.env['om.report.export']._om_cell(export, dso, export['columns'][0])
        self.assertTrue(cell.endswith('days'))

    # ------------------------------------------------------------------
    # Tax Report and Journals Audit
    # ------------------------------------------------------------------

    def taxed_invoices(self):
        sale_tax, purchase_tax = self.company_data['default_tax_sale'], self.company_data['default_tax_purchase']
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, invoice_date='2026-05-02',
                                    amounts=[1000.0], taxes=sale_tax, post=True)
        bill = self.init_invoice('in_invoice', partner=self.partner_b, invoice_date='2026-05-03',
                                 amounts=[300.0], taxes=purchase_tax, post=True)
        return sale_tax, purchase_tax, invoice, bill

    def test_tax_report_matches_the_pdf_report(self):
        sale_tax, purchase_tax, invoice, bill = self.taxed_invoices()
        report = self.env[TX].om_get_report(PERIOD, auto_unfold=True)
        base = self.env['report.accounting_pdf_reports.report_tax'].get_lines({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'target_move': 'posted',
            'used_context': {'company_id': self.env.company.id}})
        # taxes of sales and purchases may share a name: compared section by section
        for section in ('sale', 'purchase'):
            lines = {line['name']: line for line in report['children']['section-%s' % section]['lines']}
            for row in base[section]:
                self.assertAlmostEqual(lines[row['name']]['values']['base'], row['net'], 2, row['name'])
                self.assertAlmostEqual(lines[row['name']]['values']['tax'], row['tax'], 2, row['name'])
        sale_line = next(line for line in report['children']['section-sale']['lines']
                         if line['id'].endswith('tax-%s' % sale_tax.id))
        self.assertAlmostEqual(sale_line['values']['tax'], invoice.amount_tax, 2)
        self.assertAlmostEqual(report['total']['values']['tax'],
                               sum(r['tax'] for r in base['sale']) - sum(r['tax'] for r in base['purchase']), 2)
        # the tax opens its tax lines, the base its base lines
        tax_items = self.env['account.move.line'].search(
            self.env[TX].om_open_cell(report['options'], sale_line['id'], 'tax')['domain'])
        self.assertAlmostEqual(-sum(tax_items.mapped('balance')), sale_line['values']['tax'], 2)
        base_items = self.env['account.move.line'].search(
            self.env[TX].om_open_cell(report['options'], sale_line['id'], 'base')['domain'])
        self.assertAlmostEqual(-sum(base_items.mapped('balance')), sale_line['values']['base'], 2)
        accounts = self.env[TX].om_get_children(report['options'], sale_line['id'])['lines']
        self.assertAlmostEqual(sum(a['values']['tax'] for a in accounts), sale_line['values']['tax'], 2)

    def test_journals_audit(self):
        sale_tax, _purchase_tax, invoice, _bill = self.taxed_invoices()
        report = self.env[JA].om_get_report(PERIOD)
        sale_journal = invoice.journal_id
        journal = next(line for line in report['lines'] if line['id'] == 'journal-%s' % sale_journal.id)
        items = self.env['account.move.line'].search([
            ('journal_id', '=', sale_journal.id), ('parent_state', '=', 'posted'),
            ('date', '>=', '2026-01-01'), ('date', '<=', '2026-12-31')])
        self.assertAlmostEqual(journal['values']['debit'], sum(items.mapped('debit')), 2)
        self.assertAlmostEqual(report['total']['values']['debit'], report['total']['values']['credit'], 2)
        entries = self.env[JA].om_get_children(report['options'], journal['id'])['lines']
        moves = [line for line in entries if '|move-' in line['id']]
        self.assertEqual(len(moves), len(items.move_id))
        entry = next(line for line in moves if line['open']['res_id'] == invoice.id)
        self.assertAlmostEqual(entry['values']['debit'], entry['values']['credit'], 2)
        journal_items = self.env[JA].om_get_children(report['options'], entry['id'])['lines']
        self.assertEqual(len(journal_items), len(invoice.line_ids.filtered(lambda l: l.display_type != 'line_section')))
        taxes = next(line for line in entries if line['id'].endswith('|taxes'))
        tax_rows = self.env[JA].om_get_children(report['options'], taxes['id'])['lines']
        sale_row = next(row for row in tax_rows if row['name'] == sale_tax.name)
        self.assertAlmostEqual(sale_row['values']['tax'], invoice.amount_tax, 2)
        by_number = self.env[JA].om_get_children({**report['options'], 'sort_selection': 'move_name'},
                                                 journal['id'])['lines']
        names = [line['name'] for line in by_number if '|move-' in line['id']]
        self.assertEqual(names, sorted(names))

    # ------------------------------------------------------------------
    # Bank Book and Cash Book
    # ------------------------------------------------------------------

    def test_day_book(self):
        report = self.report(DB, date_from='2026-03-01', date_to='2026-04-30')
        days = {line['day']: line for line in report['lines']}
        self.assertEqual(sorted(days), ['2026-03-10', '2026-04-02'])
        march = days['2026-03-10']
        self.assertAlmostEqual(march['values']['debit'], march['values']['credit'], 2)
        self.assertAlmostEqual(march['values']['debit'], self.invoice.amount_total, 2)
        items = self.env[DB].om_get_children(report['options'], march['id'])['lines']
        self.assertEqual(len(items), len(self.invoice.line_ids))
        self.assertEqual({item['open']['res_id'] for item in items}, {self.invoice.id})
        self.assertAlmostEqual(report['total']['values']['debit'], report['total']['values']['credit'], 2)
        action = self.env[DB].om_open_line(report['options'], march['id'])
        self.assertEqual(set(self.env['account.move.line'].search(action['domain']).move_id.ids), {self.invoice.id})
        # a journal narrows it down
        bills = self.report(DB, date_from='2026-03-01', date_to='2026-04-30', journal_ids=[self.bill.journal_id.id])
        self.assertEqual([line['day'] for line in bills['lines']], ['2026-04-02'])

    def test_bank_and_cash_books(self):
        bank = self.company_data['default_journal_bank']
        cash = self.company_data['default_journal_cash']
        self.env['account.bank.statement.line'].create({
            'date': '2025-12-20', 'payment_ref': 'Opening deposit', 'amount': 700.0, 'journal_id': bank.id})
        self.env['account.bank.statement.line'].create({
            'date': '2026-02-10', 'payment_ref': 'Bank fee', 'amount': -40.0, 'journal_id': bank.id})
        self.env['account.bank.statement.line'].create({
            'date': '2026-03-01', 'payment_ref': 'Petty cash', 'amount': 120.0, 'journal_id': cash.id})
        self.pay(self.invoice, '2026-03-20')
        report = self.report(BB)
        self.assertEqual([c['label'] for c in report['columns'] if c['key'] in ('debit', 'credit')],
                         ['Receipts', 'Payments'])
        accounts = {line['id']: line for line in report['lines']}
        bank_line = accounts['account-%s' % bank.default_account_id.id]
        self.assertAlmostEqual(bank_line['values']['balance'], 660.0, 2)
        items = self.env[BB].om_get_children(report['options'], bank_line['id'])['lines']
        self.assertEqual(items[0]['kind'], 'opening')
        self.assertAlmostEqual(items[0]['values']['balance'], 700.0, 2)
        self.assertAlmostEqual(items[-1]['values']['balance'], 660.0, 2)
        # the payment registered waits on the outstanding receipts account of the bank journal
        outstanding = bank._get_journal_inbound_outstanding_payment_accounts()
        self.assertTrue(any(line['id'] == 'account-%s' % account.id for account in outstanding
                            for line in report['lines']))
        # nothing of the cash journal, nor of the other accounts
        self.assertNotIn('account-%s' % cash.default_account_id.id, accounts)
        self.assertNotIn('account-%s' % self.receivable.id, accounts)
        self.assertNotIn('all', [value for choice in report['choices'] if choice['key'] == 'display_account'
                                 for value, _label in choice['choices']])
        cash_report = self.report(CB)
        self.assertEqual([line['id'] for line in cash_report['lines']], ['account-%s' % cash.default_account_id.id])
        self.assertAlmostEqual(cash_report['total']['values']['balance'], 120.0, 2)

    # ------------------------------------------------------------------
    # Bank Reconciliation
    # ------------------------------------------------------------------

    def test_bank_reconciliation(self):
        bank = self.company_data['default_journal_bank']
        statement = self.env['account.bank.statement'].create({
            'name': 'Statement 1', 'journal_id': bank.id, 'date': '2026-06-30', 'balance_start': 0.0,
            'balance_end_real': 300.0,
            'line_ids': [(0, 0, {'date': '2026-06-10', 'payment_ref': 'Deposit', 'amount': 500.0,
                                 'journal_id': bank.id}),
                         (0, 0, {'date': '2026-06-20', 'payment_ref': 'Fee', 'amount': -200.0,
                                 'journal_id': bank.id})]})
        # a transaction after the statement, in no statement
        self.env['account.bank.statement.line'].create({
            'date': '2026-07-05', 'payment_ref': 'Late deposit', 'amount': 50.0, 'journal_id': bank.id})
        # a payment registered and not yet seen on the bank
        self.pay(self.invoice, '2026-07-10')
        report = self.env[BR].om_get_report({'date_preset': 'custom', 'date_to': '2026-12-31',
                                             'journal_ids': [bank.id]}, auto_unfold=True)
        rows = {line['id'].split('|', 1)[1]: line for line in report['children']['journal-%s' % bank.id]['lines']}
        value = lambda key: rows[key]['values']['amount']  # noqa: E731
        self.assertAlmostEqual(value('books'), 350.0, 2)
        self.assertEqual(rows['statement']['open'], {'res_model': 'account.bank.statement', 'res_id': statement.id})
        self.assertAlmostEqual(value('statement'), 300.0, 2)
        self.assertAlmostEqual(value('not_on_statement'), 50.0, 2)
        self.assertAlmostEqual(value('unmatched_receipts'), 550.0, 2)
        self.assertAlmostEqual(value('unmatched_payments'), -200.0, 2)
        self.assertAlmostEqual(value('outstanding_receipts'), self.invoice.amount_total, 2)
        self.assertAlmostEqual(value('once_matched'), 350.0 + self.invoice.amount_total, 2)
        items = self.env[BR].om_get_children(report['options'], rows['unmatched_payments']['id'])['lines']
        self.assertEqual([item['values']['label'] for item in items], ['Fee'])
        # at the end of June: the late deposit and the payment did not exist yet
        june = self.env[BR].om_get_report({'date_preset': 'custom', 'date_to': '2026-06-30',
                                           'journal_ids': [bank.id]}, auto_unfold=True)
        june_rows = {line['id'].split('|', 1)[1]: line for line in june['children']['journal-%s' % bank.id]['lines']}
        self.assertAlmostEqual(june_rows['not_on_statement']['values']['amount'], 0.0, 2)
        self.assertAlmostEqual(june_rows['outstanding_receipts']['values']['amount'], 0.0, 2)
        action = self.env[BR].om_open_line(report['options'], rows['not_on_statement']['id'])
        late = self.env['account.move.line'].search(action['domain'])
        self.assertAlmostEqual(sum(late.mapped('balance')), 50.0, 2)

    # ------------------------------------------------------------------
    # Customer and Vendor Statements
    # ------------------------------------------------------------------

    def test_customer_statement_activity(self):
        self.pay(self.invoice, '2026-03-20')
        report = self.env[CS].om_get_report({**PERIOD, 'partner_ids': [self.partner_a.id]}, auto_unfold=True)
        partner_id = 'partner-%s' % self.partner_a.id
        self.assertIn(partner_id, report['expanded'])
        rows = report['children'][partner_id]['lines']
        self.assertEqual(rows[0]['kind'], 'opening')
        self.assertAlmostEqual(rows[0]['values']['balance'], self.old_invoice.amount_total, 2)
        details = [row for row in rows if row['kind'] == 'detail']
        self.assertEqual(len(details), 2)
        self.assertAlmostEqual(details[0]['values']['charge'], self.invoice.amount_total, 2)
        self.assertAlmostEqual(details[1]['values']['payment'], self.invoice.amount_total, 2)
        closing = next(row for row in rows if row['kind'] == 'closing')
        self.assertAlmostEqual(closing['values']['balance'], self.old_invoice.amount_total, 2)
        self.assertAlmostEqual(details[-1]['values']['balance'], closing['values']['balance'], 2)
        # what is due is last year's invoice, overdue for more than 120 days
        ageing = [row for row in rows if row['id'].rsplit('|', 1)[1].startswith('ageing-')]
        self.assertEqual([row['name'] for row in ageing], ['Overdue more than 120 days'])
        self.assertAlmostEqual(ageing[0]['values']['balance'], self.old_invoice.amount_total, 2)

    def test_statement_open_items_and_vendor(self):
        report = self.env[CS].om_get_report({**PERIOD, 'statement_type': 'open'}, auto_unfold=True)
        partner_id = 'partner-%s' % self.partner_a.id
        rows = report['children'][partner_id]['lines']
        self.assertEqual({row['open']['res_id'] for row in rows if row['kind'] == 'detail'},
                         {self.old_invoice.id, self.invoice.id})
        vendor = self.env[VS].om_get_report({**PERIOD, 'partner_ids': [self.partner_b.id]})
        self.assertAlmostEqual(vendor['lines'][0]['values']['balance'], self.bill.amount_total, 2)
        self.assertAlmostEqual(vendor['lines'][0]['values']['charge'], self.bill.amount_total, 2)
        self.assertEqual(vendor['columns'][3]['label'], 'Billed')

    def test_statement_buttons(self):
        options = {**PERIOD, 'partner_ids': [self.partner_a.id]}
        report = self.env[CS].om_get_report(options)
        line = report['lines'][0]
        self.assertEqual([button['key'] for button in line['actions']], ['download', 'email'])
        download = self.env[CS].om_line_button(report['options'], line['id'], 'download')
        self.assertEqual(download['type'], 'ir.actions.act_url')
        attachment = self.env['ir.attachment'].browse(int(download['url'].split('/')[3].split('?')[0]))
        self.assertEqual(attachment.mimetype, 'application/pdf')
        email = self.env[CS].om_line_button(report['options'], line['id'], 'email')
        self.assertEqual(email['res_model'], 'mail.compose.message')
        self.assertEqual(email['context']['default_partner_ids'], [self.partner_a.id])
        sent = self.env['ir.attachment'].browse(email['context']['default_attachment_ids'][0][2])
        self.assertEqual((sent.res_model, sent.res_id), ('res.partner', self.partner_a.id))
        export = self.env[CS].om_export_data(report['options'], expand_all=True)
        self.assertEqual(export['recipient'], self.partner_a)

    # ------------------------------------------------------------------
    # Analytic columns
    # ------------------------------------------------------------------

    def analytic_setup(self):
        self.env.user.group_ids |= self.env.ref('analytic.group_analytic_accounting')
        plan = self.env['account.analytic.plan'].create({'name': 'Regions'})
        north, south = self.env['account.analytic.account'].create([
            {'name': 'North', 'plan_id': plan.id}, {'name': 'South', 'plan_id': plan.id}])
        for distribution, amount in (({str(north.id): 60, str(south.id): 40}, 1000.0),
                                     ({str(north.id): 100}, 200.0), (False, 50.0)):
            invoice = self.init_invoice('out_invoice', partner=self.partner_a, invoice_date='2026-09-01',
                                        amounts=[amount])
            invoice.invoice_line_ids.analytic_distribution = distribution
            invoice.action_post()
        return plan, north, south

    def test_profit_and_loss_analytic_columns(self):
        plan, north, south = self.analytic_setup()
        report = self.report(PNL, analytic_column_ids=[north.id, south.id], analytic_plan_column_ids=[plan.id])
        keys = [column['key'] for column in report['columns']]
        north_key, south_key, plan_key = 'an_a%s' % north.id, 'an_a%s' % south.id, 'an_p%s' % plan.id
        self.assertEqual(keys, [north_key, south_key, plan_key, 'balance'])
        self.assertEqual({column['group'] for column in report['columns']}, {'01/01/2026 - 12/31/2026'})
        total = report['total']['values']
        self.assertAlmostEqual(total[north_key], 600.0 + 200.0, 2)
        self.assertAlmostEqual(total[south_key], 400.0, 2)
        self.assertAlmostEqual(total[plan_key], 1200.0, 2)
        # the total of the period is every entry, with or without analytic
        self.assertAlmostEqual(total['balance'], 400.0 - 250.0 + 1250.0, 2)
        lines = self.statement_lines(PNL, report)
        revenue = next(line for name, line in lines.items() if name.startswith(self.revenue.code))
        self.assertAlmostEqual(revenue['values'][north_key], 800.0, 2)

        compared = self.report(PNL, analytic_column_ids=[north.id], compare='previous_year')
        self.assertEqual([c['key'] for c in compared['columns']],
                         [north_key, 'balance', north_key + '_1', 'balance_1'])
        self.assertAlmostEqual(compared['total']['values'][north_key + '_1'], 0.0, 2)

    def test_cell_drill_down(self):
        plan, north, _south = self.analytic_setup()
        report = self.report(PNL, analytic_column_ids=[north.id], compare='previous_year')
        lines = self.statement_lines(PNL, report)
        revenue = next(line for name, line in lines.items() if name.startswith(self.revenue.code))
        north_key = 'an_a%s' % north.id
        self.assertTrue(next(c for c in report['columns'] if c['key'] == north_key)['drill'])
        # an analytic figure opens the analytic lines making it: the weighted shares
        action = self.env[PNL].om_open_cell(report['options'], revenue['id'], north_key)
        self.assertEqual(action['res_model'], 'account.analytic.line')
        analytic_lines = self.env['account.analytic.line'].search(action['domain'])
        self.assertAlmostEqual(sum(analytic_lines.mapped('amount')), revenue['values'][north_key], 2)
        self.assertEqual(set(analytic_lines.mapped('general_account_id').ids), {self.revenue.id})
        # the total of a compared period opens the journal items of that period
        action = self.env[PNL].om_open_cell(report['options'], revenue['id'], 'balance_1')
        items = self.env['account.move.line'].search(action['domain'])
        self.assertTrue(all(item.date.year == 2025 for item in items))
        self.assertAlmostEqual(-sum(items.mapped('balance')), revenue['values']['balance_1'], 2)

        tb = self.report(TB)
        receivable = next(line for line in tb['lines'] if line['id'] == 'account-%s' % self.receivable.id)
        for key, value_key in (('init_debit', 'init_balance'), ('debit', None), ('end_debit', 'end_balance')):
            action = self.env[TB].om_open_cell(tb['options'], receivable['id'], key)
            items = self.env['account.move.line'].search(action['domain'])
            if value_key:
                self.assertAlmostEqual(sum(items.mapped('balance')), receivable['values'][value_key], 2, key)
            else:
                self.assertAlmostEqual(sum(items.mapped('debit')), receivable['values']['debit'], 2, key)
        # a column that is not drillable opens nothing
        self.assertFalse(self.env[PNL].om_open_cell(self.report(PNL, compare='previous_year')['options'],
                                                    revenue['id'], 'variation'))

    def test_trial_balance_analytic_columns(self):
        plan, north, _south = self.analytic_setup()
        report = self.report(TB, analytic_column_ids=[north.id])
        key = 'an_a%s' % north.id
        movement_columns = [c['key'] for c in report['columns'] if c['group'] == '01/01/2026 - 12/31/2026']
        self.assertEqual(movement_columns, ['debit', 'credit', 'balance', key])
        revenue = next(line for line in report['lines'] if line['id'] == 'account-%s' % self.revenue.id)
        self.assertAlmostEqual(revenue['values'][key], -800.0, 2)
        self.assertAlmostEqual(report['total']['values'][key], 0.0 - 800.0, 2)

    # ------------------------------------------------------------------
    # Analytic Report: rows grouped by the engine
    # ------------------------------------------------------------------

    def test_analytic_report(self):
        self.env.user.group_ids |= self.env.ref('analytic.group_analytic_accounting')
        plan = self.env['account.analytic.plan'].create({'name': 'Projects'})
        alpha, beta = self.env['account.analytic.account'].create([
            {'name': 'Alpha', 'plan_id': plan.id}, {'name': 'Beta', 'plan_id': plan.id}])
        for analytic, amount in ((alpha, 300.0), (alpha, 200.0), (beta, 50.0)):
            invoice = self.init_invoice('out_invoice', partner=self.partner_a, invoice_date='2026-08-01',
                                        amounts=[amount])
            invoice.invoice_line_ids.analytic_distribution = {str(analytic.id): 100}
            invoice.action_post()
        report = self.report(AN, group_by=['analytic_account', 'partner'], analytic_plan=str(plan.id))
        self.assertEqual([line['name'] for line in report['lines']], ['Alpha', 'Beta'])
        alpha_line = report['lines'][0]
        self.assertAlmostEqual(alpha_line['values']['income'], 500.0, 2)
        self.assertAlmostEqual(report['total']['values']['balance'], 550.0, 2)
        partners = self.children(AN, report, alpha_line)['lines']
        self.assertEqual([line['name'] for line in partners], [self.partner_a.display_name])
        details = self.children(AN, report, partners[0])['lines']
        self.assertEqual(len(details), 2)
        self.assertEqual({line['kind'] for line in details}, {'detail'})

        by_balance = self.report(AN, group_by=['analytic_account'], analytic_plan=str(plan.id),
                                 sort={'key': 'balance', 'dir': 'asc'})
        self.assertEqual([line['name'] for line in by_balance['lines']], ['Beta', 'Alpha'])
        searched = self.report(AN, group_by=['analytic_account'], analytic_plan=str(plan.id), search='bet')
        self.assertEqual([line['name'] for line in searched['lines']], ['Beta'])

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

    def test_several_companies_in_another_currency(self):
        eur = self.setup_other_currency('EUR', rates=[('2016-01-01', 2.0)])
        other = self.setup_other_company(name='Company EUR', currency_id=eur.id)
        company = other['company']
        self.env.user.company_ids |= company
        invoice = self.env['account.move'].with_company(company).create({
            'move_type': 'out_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2026-05-01',
            'invoice_line_ids': [(0, 0, {'name': 'Service', 'price_unit': 200.0, 'tax_ids': False,
                                         'account_id': other['default_account_revenue'].id})],
        })
        invoice.action_post()
        both = self.env.company | company
        # the client always says which companies are selected; without it Odoo takes all of the user's
        main = self.env[TB].with_context(allowed_company_ids=self.env.company.ids)
        alone = main.om_get_report(PERIOD)['total']['values']
        together = self.env[TB].with_context(allowed_company_ids=both.ids).om_get_report(PERIOD)['total']['values']
        # 200 EUR at 2 EUR for 1 USD
        self.assertAlmostEqual(together['debit'] - alone['debit'], 100.0, 2)
        self.assertAlmostEqual(together['end_debit'], together['end_credit'], 2)
        lines = self.env[TB].with_context(allowed_company_ids=both.ids).om_get_report(PERIOD)['lines']
        revenue_2 = other['default_account_revenue']
        line = next(line for line in lines if line['id'] == 'account-%s' % revenue_2.id)
        # the code of an account of the other company, read in its company
        self.assertTrue(line['name'].startswith(revenue_2.with_company(company).code))
        self.assertTrue(line['name'].endswith('(Company EUR)'))
        net = self.env[PNL].with_context(allowed_company_ids=both.ids).om_get_report(PERIOD)['total']['values']
        self.assertAlmostEqual(net['balance'], 150.0 + 100.0, 2)
        aged = self.env[AR].with_context(allowed_company_ids=both.ids).om_get_report(
            {'date_preset': 'custom', 'date_to': '2026-12-31'})
        partner = next(line for line in aged['lines'] if line['id'] == 'partner-%s' % self.partner_a.id)
        self.assertAlmostEqual(partner['values']['total'],
                               self.old_invoice.amount_total + self.invoice.amount_total + 100.0, 2)
        cash_alone = main.env[CF].om_get_report(PERIOD)['total']
        cash_both = self.env[CF].with_context(allowed_company_ids=both.ids).om_get_report(PERIOD)['total']
        # no cash moved in the other company: the statement of both is the one of the main company
        self.assertEqual(bool(cash_alone), bool(cash_both))
        if cash_alone:
            self.assertAlmostEqual(cash_both['values']['balance'], cash_alone['values']['balance'], 2)
        summary = dict(self.env[TB].with_context(allowed_company_ids=both.ids).om_export_data(PERIOD)['filters'])
        self.assertIn('Company EUR', summary['Companies'])
        self.assertTrue(summary['Currency'].startswith(self.env.company.currency_id.name))
        # the company of the report alone is not converted, and says nothing about currencies
        self.assertNotIn('Currency', dict(main.om_export_data(PERIOD)['filters']))

    def test_notes_on_figures(self):
        report = self.report(PNL)
        revenue = next(line for name, line in self.statement_lines(PNL, report).items()
                       if name.startswith(self.revenue.code))
        notes = self.env[PNL].om_save_note(report['options'], revenue['id'], 'balance', 'Big March sale')
        self.assertEqual([note['note'] for note in notes], ['Big March sale'])
        self.assertTrue(notes[0]['mine'])
        again = self.statement_lines(PNL, self.report(PNL))
        self.assertEqual(again[revenue['name']]['notes']['balance'][0]['note'], 'Big March sale')
        # the figure of 2026 compared from 2027 carries the note; the one of 2027 does not
        next_year = self.statement_lines(PNL, self.report(PNL, date_from='2027-01-01', date_to='2027-12-31',
                                                          compare='previous_year'))
        line = next_year.get(revenue['name'])
        if line:
            self.assertIn('balance_1', line.get('notes', {}))
            self.assertNotIn('balance', line.get('notes', {}))
        # another user reads it, and cannot change it
        other = new_test_user(self.env, login='odr_reader', groups='account.group_account_readonly',
                              company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        read = self.env[PNL].with_user(other).om_get_notes(report['options'], revenue['id'], 'balance')
        self.assertFalse(read[0]['mine'])
        self.env[PNL].with_user(other).om_save_note(report['options'], revenue['id'], 'balance', 'Hacked',
                                                    note_id=read[0]['id'])
        self.env[PNL].with_user(other).om_delete_note(read[0]['id'])
        self.assertEqual([n['note'] for n in self.env[PNL].om_get_notes(report['options'], revenue['id'], 'balance')],
                         ['Big March sale'])
        # the exports carry it
        export = self.env[PNL].om_export_data(report['options'], expand_all=True)
        self.assertEqual([n['note'] for n in export['notes']], ['Big March sale'])
        content, _name, _type = self.env['om.report.export']._om_render_file(
            {'model': PNL, 'format': 'xlsx', 'options': report['options'], 'expand_all': True})
        self.assertTrue(content)
        # the author deletes it
        self.env[PNL].om_delete_note(notes[0]['id'])
        self.assertFalse(self.env[PNL].om_get_notes(report['options'], revenue['id'], 'balance'))

    def test_presentation_currency(self):
        eur = self.setup_other_currency('EUR', rates=[('2025-12-31', 0.5), ('2026-06-30', 1.0)])
        self.pay(self.invoice, '2026-03-20')
        bank = self.company_data['default_journal_bank']
        for payment in self.invoice.matched_payment_ids:
            payment.move_id.line_ids.filtered(
                lambda l: l.account_id == payment.outstanding_account_id).account_id = bank.default_account_id
        choices = {c['key']: c for c in self.report(TB)['choices']}
        self.assertIn(str(eur.id), [value for value, _label in choices['presentation_currency']['choices']])
        in_eur = {'presentation_currency': str(eur.id)}
        # income and expense at the average rate of their months: March and April at 0.5
        pnl = self.report(PNL, **in_eur)
        self.assertEqual(pnl['currency_id'], eur.id)
        self.assertAlmostEqual(pnl['total']['values']['balance'], (400.0 - 250.0) * 0.5, 2)
        # the balance sheet at the closing rate, balanced by the translation adjustment in the equity
        bs = self.statement_lines(BS, self.report(BS, date_preset='custom', date_to='2026-12-31', **in_eur))
        self.assertAlmostEqual(bs['Assets']['values']['balance'], bs['Liabilities and Equity']['values']['balance'], 2)
        self.assertIn('Currency translation adjustment', bs)
        # the earnings at the rates they were earned at: last year's invoice, this year's invoice and bill
        self.assertAlmostEqual(bs['Previous Years Unallocated Earnings']['values']['balance'], 1000.0 * 0.5, 2)
        self.assertAlmostEqual(bs['Current Year Unallocated Earnings']['values']['balance'], 150.0 * 0.5, 2)
        receivable_eur = next(line for name, line in bs.items() if name.startswith(self.receivable.code))
        receivable_usd = next(line for name, line in self.statement_lines(
            BS, self.report(BS, date_preset='custom', date_to='2026-12-31')).items()
            if name.startswith(self.receivable.code))
        self.assertAlmostEqual(receivable_eur['values']['balance'], receivable_usd['values']['balance'] * 1.0, 2)
        # the cash: what the rates did to it is a line of its own
        for method in ('direct', 'indirect'):
            cash = self.statement_lines(CF, self.report(CF, method=method, **in_eur))
            report = self.report(CF, method=method, **in_eur)
            fx = cash.get('Effect of exchange rate changes on cash', {'values': {'balance': 0.0}})['values']['balance']
            self.assertAlmostEqual(cash['Cash at the beginning of the period']['values']['balance']
                                   + cash['Net change in cash']['values']['balance'] + fx,
                                   report['total']['values']['balance'], 2, method)
        # the executive summary agrees with the profit and loss
        summary = self.env[ES].om_get_report({**PERIOD, **in_eur}, auto_unfold=True)
        net = next(line for line in summary['children']['section-profitability']['lines']
                   if line['id'].endswith('figure-net_profit'))
        self.assertAlmostEqual(net['values']['value'], pnl['total']['values']['balance'], 2)
        label = dict(self.env[PNL].om_export_data({**PERIOD, **in_eur})['filters'])['Currency']
        self.assertIn('average rates', label)

    def test_folds_per_user(self):
        Fold = self.env['om.report.fold']
        self.assertFalse(Fold.om_get(GL))
        Fold.om_set(GL, ['account-%s' % self.receivable.id])
        self.assertEqual(Fold.om_get(GL), ['account-%s' % self.receivable.id])
        Fold.om_set(GL, [])
        self.assertEqual(Fold.om_get(GL), [], "folding everything is remembered too")
        other = new_test_user(self.env, login='odr_folder', groups='account.group_account_readonly',
                              company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        self.assertFalse(Fold.with_user(other).om_get(GL), "each user has their own folds")
        Fold.with_user(other).om_set(GL, ['account-1'])
        self.assertEqual(Fold.om_get(GL), [])
        self.assertEqual(Fold.search_count([('report_model', '=', GL)]), 1, "a user does not see the folds of another")
        with self.assertRaises(Exception):
            Fold.om_set('res.partner', ['x'])
        # the remembered folds open the report that way
        report = self.env[GL].om_get_report(PERIOD, expanded=['account-%s' % self.receivable.id])
        self.assertEqual(report['expanded'], ['account-%s' % self.receivable.id])

    def test_review_fixes(self):
        # the base of the two books is no report of the switcher
        catalog = [entry['model'] for entry in self.env['om.report'].om_get_catalog('accounting')]
        self.assertNotIn('om.dynamic.report.book', catalog)
        self.assertIn(BB, catalog)
        # a deleted note does not come back from the cache
        report = self.report(TB)
        line = next(line for line in report['lines'] if line['id'] == 'account-%s' % self.receivable.id)
        note = self.env[TB].om_save_note(report['options'], line['id'], 'debit', 'To check')[0]
        self.report(TB)
        self.env[TB].om_delete_note(note['id'])
        self.assertFalse(self.env[TB].om_export_data(report['options'])['notes'])
        self.assertNotIn('notes', next(l for l in self.report(TB)['lines'] if l['id'] == line['id']))
        # a compared period is converted at its own rates
        eur = self.setup_other_currency('EUR', rates=[('2024-12-31', 0.5), ('2025-12-31', 1.0)])
        compared = self.report(PNL, compare='previous_year', presentation_currency=str(eur.id))
        self.assertAlmostEqual(compared['total']['values']['balance_1'], 1000.0 * 0.5, 2)
        self.assertAlmostEqual(compared['total']['values']['balance'], 150.0 * 1.0, 2)
        # the columns: in the order chosen, shown and hidden, the others as by default
        keys = ['end_credit', 'end_debit', 'init_debit']
        ordered = self.report(TB, columns={'order': keys, 'shown': ['balance'], 'hidden': ['init_credit']})
        columns = {c['key']: c for c in ordered['columns']}
        self.assertEqual([c['key'] for c in ordered['columns']][:3], keys)
        self.assertTrue(columns['balance']['visible'])
        self.assertFalse(columns['init_credit']['visible'])
        self.assertFalse(columns['end_balance']['visible'])
        with_comparison = self.report(TB, compare='previous_year', columns={'hidden': ['init_credit']})
        self.assertTrue({c['key']: c for c in with_comparison['columns']}['debit_1']['visible'])
        # the notes are reached through the reports only
        other = new_test_user(self.env, login='odr_curious', groups='base.group_user',
                              company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        with self.assertRaises(AccessError):
            self.env['om.report.note'].with_user(other).search([])

    def test_access(self):
        billing = new_test_user(self.env, login='odr_billing', groups='account.group_account_invoice',
                                company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        catalog = self.env['om.report'].with_user(billing).om_get_catalog('accounting')
        self.assertEqual([entry['model'] for entry in catalog], [PL, AR, AP, CS, VS])
        self.env[PL].with_user(billing).om_get_report(PERIOD)
        with self.assertRaises(AccessError):
            self.env[TB].with_user(billing).om_get_report(PERIOD)

    def test_options_are_normalized(self):
        options = self.report(TB, display_account='bogus', journal_ids=['x', '3'], unknown=1)['options']
        self.assertEqual(options['display_account'], 'movement')
        self.assertEqual(options['journal_ids'], [3])
        self.assertNotIn('unknown', options)

    def test_fiscal_year_presets(self):
        self.env.company.write({'fiscalyear_last_month': '3', 'fiscalyear_last_day': 31})
        with patch('odoo.fields.Date.context_today', return_value=__import__('datetime').date(2026, 11, 15)):
            options = self.env[TB].om_get_report({'date_preset': 'this_year'})['options']
        self.assertEqual((options['date_from'], options['date_to']), ('2026-04-01', '2027-03-31'))

    def test_exports(self):
        exporter = self.env['om.report.export']
        for model in (TB, GL, PL):
            for file_format in ('xlsx', 'csv'):
                content, filename, _mimetype = exporter._om_render_file(
                    {'model': model, 'format': file_format, 'options': PERIOD, 'expand_all': True})
                self.assertTrue(content, '%s %s' % (model, file_format))
                self.assertTrue(filename.endswith('.' + file_format))
        export = self.env[GL].om_export_data(PERIOD, expand_all=True)
        self.assertTrue(any(line['kind'] == 'detail' for line in export['lines']))
        self.assertIn(('Entries', 'Posted entries'), export['filters'])

    def test_export_refuses_other_models(self):
        with self.assertRaises(Exception):
            self.env['om.report.export']._om_render_file({'model': 'res.users', 'format': 'csv', 'options': {}})

    def test_saved_views(self):
        View = self.env['om.report.view']
        view_id = View.om_save(TB, 'Mine', {**PERIOD, 'date_preset': 'this_year', 'display_account': 'all',
                                            'garbage': 1}, is_default=True)
        view = View.browse(view_id)
        self.assertEqual(view.options, {'date_preset': 'this_year', 'display_account': 'all'})
        self.assertTrue(View.om_list(TB)[0]['is_default'])
