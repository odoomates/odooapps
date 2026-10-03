from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBudgetLine(TransactionCase):

    def test_the_analytic_plan_of_a_budget_line(self):
        plan = self.env['account.analytic.plan'].create({'name': 'Projects'})
        analytic = self.env['account.analytic.account'].create({'name': 'Project 1', 'plan_id': plan.id})
        account = self.env['account.account'].create({
            'name': 'Budget Expenses', 'code': '699990', 'account_type': 'expense'})
        position = self.env['account.budget.post'].create({'name': 'Expenses', 'account_ids': [(6, 0, account.ids)]})
        budget = self.env['crossovered.budget'].create({
            'name': 'Budget 2026',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'crossovered_budget_line': [(0, 0, {
                'analytic_account_id': analytic.id,
                'general_budget_id': position.id,
                'date_from': '2026-01-01',
                'date_to': '2026-12-31',
                'planned_amount': 1000,
            })],
        })
        Lines = self.env['crossovered.budget.lines']
        self.assertEqual(budget.crossovered_budget_line.analytic_plan_id, plan)
        self.assertEqual(budget.crossovered_budget_line.read(['analytic_plan_id'])[0]['analytic_plan_id'][0], plan.id)
        self.assertEqual(Lines.search([('id', 'in', budget.crossovered_budget_line.ids)], order='analytic_plan_id'),
                         budget.crossovered_budget_line)
        self.assertTrue(Lines.fields_get(['analytic_plan_id']))
