from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

DR = 'om.dynamic.report.deferred.revenue'
DE = 'om.dynamic.report.deferred.expense'
DS = 'om.dynamic.report.depreciation'
PERIOD = {'date_preset': 'custom', 'date_from': '2026-04-01', 'date_to': '2026-06-30'}


@tagged('post_install', '-at_install')
class TestDeferredReports(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('account.group_account_readonly')
        Account = cls.env['account.account']
        deferred_revenue = Account.create({
            'code': '255000', 'name': 'Deferred Revenue', 'account_type': 'liability_current'})
        prepaid = Account.create({'code': '148000', 'name': 'Prepaid Expenses', 'account_type': 'asset_prepayments'})
        equipment = Account.create({'code': '151100', 'name': 'Equipment', 'account_type': 'asset_fixed'})
        accumulated = Account.create({
            'code': '151900', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        journal = cls.company_data['default_journal_misc']
        Category = cls.env['account.asset.category']
        common = {'journal_id': journal.id, 'method_number': 12, 'method_period': 1,
                  'date_first_depreciation': 'last_day_period', 'open_asset': True}
        cls.revenue_category = Category.create({
            **common, 'name': 'Support Contracts', 'type': 'sale', 'account_asset_id': deferred_revenue.id,
            'account_depreciation_id': deferred_revenue.id,
            'account_depreciation_expense_id': cls.company_data['default_account_revenue'].id})
        cls.prepaid_category = Category.create({
            **common, 'name': 'Prepaid Insurance', 'type': 'purchase', 'account_asset_id': prepaid.id,
            'account_depreciation_id': prepaid.id,
            'account_depreciation_expense_id': cls.company_data['default_account_expense'].id})
        cls.fixed_category = Category.create({
            **common, 'name': 'Equipment', 'type': 'purchase', 'account_asset_id': equipment.id,
            'account_depreciation_id': accumulated.id,
            'account_depreciation_expense_id': cls.company_data['default_account_expense'].id})

    def deferral(self, category, name, validate_on='2025-12-15', **vals):
        asset = self.env['account.asset.asset'].create({
            'name': name, 'category_id': category.id, 'value': 1200.0, 'date': date(2026, 1, 1),
            'method': 'linear', 'method_time': 'number', 'method_number': 12, 'method_period': 1,
            'date_first_depreciation': 'last_day_period', 'partner_id': self.partner_a.id, **vals})
        asset.validate()
        # the entries of the board due on that day
        asset._compute_entries(date.fromisoformat(validate_on))
        return asset

    def report(self, model, **options):
        return self.env[model].om_get_report({**PERIOD, **options}, auto_unfold=True)

    def test_deferred_revenue_schedule(self):
        asset = self.deferral(self.revenue_category, 'Support 2026', validate_on='2026-06-15')
        report = self.report(DR)
        keys = [column['key'] for column in report['columns']]
        self.assertEqual(keys, ['start', 'total', 'before', 'p_20260401', 'p_20260501', 'p_20260601', 'later'])
        category = report['lines'][0]
        self.assertEqual(category['name'], 'Support Contracts')
        row = report['children'][category['id']]['lines'][0]
        self.assertEqual(row['open'], {'res_model': 'account.asset.asset', 'res_id': asset.id})
        values = row['values']
        self.assertAlmostEqual(values['total'], 1200.0, 2)
        self.assertAlmostEqual(values['before'], 300.0, 2)
        for key in ('p_20260401', 'p_20260501', 'p_20260601'):
            self.assertAlmostEqual(values[key], 100.0, 2)
        self.assertAlmostEqual(values['later'], 600.0, 2)
        self.assertAlmostEqual(report['total']['values']['total'], 1200.0, 2)
        # a month opens its recognition entry
        action = self.env[DR].om_open_cell(report['options'], row['id'], 'p_20260501')
        moves = self.env['account.move'].search(action['domain'])
        self.assertEqual(moves.mapped('date'), [date(2026, 5, 31)])

    def test_posted_recognitions_only(self):
        self.deferral(self.revenue_category, 'Support 2026', validate_on='2026-07-15')
        values = self.report(DR, recognition='posted')
        row = values['children'][values['lines'][0]['id']]['lines'][0]['values']
        self.assertAlmostEqual(row['total'], 600.0, 2)
        self.assertAlmostEqual(row['later'], 0.0, 2)

    def test_deferred_expense_leaves_the_fixed_assets_out(self):
        self.deferral(self.prepaid_category, 'Insurance 2026')
        self.deferral(self.fixed_category, 'Laptop')
        report = self.report(DE)
        self.assertEqual([line['name'] for line in report['lines']], ['Prepaid Insurance'])
        self.assertFalse(self.report(DR)['lines'])
        self.assertIn('Prepaid Insurance', [c['display_name'] for c in self.env['account.asset.category'].search(
            self.env[DE]._odr_category_domain()).read(['display_name'])])

    def test_quarters_for_a_long_period(self):
        self.deferral(self.revenue_category, 'Support 2026')
        report = self.report(DR, date_from='2025-01-01', date_to='2027-12-31')
        periods = [column['label'] for column in report['columns'] if column['key'].startswith('p_')]
        self.assertEqual(len(periods), 12)
        self.assertEqual(periods[0], 'Q1 2025')

    def test_depreciation_schedule(self):
        self.deferral(self.fixed_category, 'Laptop', validate_on='2026-07-15')
        self.deferral(self.prepaid_category, 'Insurance 2026')
        report = self.report(DS, recognition='posted')
        self.assertEqual([line['name'] for line in report['lines']], ['Equipment'], "only the fixed assets")
        row = report['children'][report['lines'][0]['id']]['lines'][0]['values']
        # acquired on 2026-01-01, 100 a month, posted until June: 300 before April, 300 in April-June
        self.assertAlmostEqual(row['gross_opening'], 1200.0, 2)
        self.assertAlmostEqual(row['gross_additions'], 0.0, 2)
        self.assertAlmostEqual(row['gross_closing'], 1200.0, 2)
        self.assertAlmostEqual(row['dep_opening'], 300.0, 2)
        self.assertAlmostEqual(row['dep_period'], 300.0, 2)
        self.assertAlmostEqual(row['dep_closing'], 600.0, 2)
        self.assertAlmostEqual(row['book_value'], 600.0, 2)
        # acquired within the period: an addition
        whole_year = self.report(DS, date_from='2026-01-01', date_to='2026-12-31', recognition='all')
        values = whole_year['children'][whole_year['lines'][0]['id']]['lines'][0]['values']
        self.assertAlmostEqual(values['gross_opening'], 0.0, 2)
        self.assertAlmostEqual(values['gross_additions'], 1200.0, 2)
        self.assertAlmostEqual(values['dep_period'], 1200.0, 2)
        self.assertAlmostEqual(values['book_value'], 0.0, 2)
        # the depreciation of the period opens its entries
        line = report['children'][report['lines'][0]['id']]['lines'][0]
        moves = self.env['account.move'].search(self.env[DS].om_open_cell(report['options'], line['id'],
                                                                         'dep_period')['domain'])
        self.assertAlmostEqual(sum(moves.asset_depreciation_ids.mapped('amount')), 300.0, 2)

    def test_depreciation_schedule_disposal(self):
        laptop = self.deferral(self.fixed_category, 'Laptop', validate_on='2026-07-15')
        with freeze_time('2026-08-20'):
            laptop.dispose(disposal_date=date(2026, 8, 15))
        report = self.report(DS, date_from='2026-07-01', date_to='2026-12-31', recognition='posted')
        values = report['children'][report['lines'][0]['id']]['lines'][0]['values']
        self.assertAlmostEqual(values['gross_disposals'], 1200.0, 2)
        self.assertAlmostEqual(values['gross_closing'], 0.0, 2)
        self.assertAlmostEqual(values['dep_closing'], 0.0, 2)
        self.assertAlmostEqual(values['dep_disposals'], values['dep_opening'] + values['dep_period'], 2)
