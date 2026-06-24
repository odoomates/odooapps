from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestAccountBudget(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestAccountBudget, cls).setUpClass()
        cls.account_model = cls.env['account.account']
        cls.budget_post_model = cls.env['account.budget.post']
        cls.budget_model = cls.env['crossovered.budget']
        
        # Create a test account
        cls.test_account = cls.account_model.create({
            'name': 'Test Account',
            'code': '123456',
            'account_type': 'expense',
        })

    def test_01_budget_post_creation(self):
        """Test the creation and validation of a budgetary position."""
        
        # Scenario 1.1: Create without accounts should fail
        with self.assertRaises(ValidationError):
            self.budget_post_model.create({
                'name': 'Empty Budget Post',
                'account_ids': [(5, 0, 0)]
            })

        # Scenario 1.2: Create with accounts should succeed
        budget_post = self.budget_post_model.create({
            'name': 'Valid Budget Post',
            'account_ids': [(4, self.test_account.id)]
        })
        self.assertTrue(budget_post.id)
        self.assertEqual(len(budget_post.account_ids), 1)

        # Scenario 1.3: Remove accounts from existing should fail
        with self.assertRaises(ValidationError):
            budget_post.write({'account_ids': [(5, 0, 0)]})

    def test_02_budget_state_transitions(self):
        """Test the workflow and state transitions of a budget."""
        budget = self.budget_model.create({
            'name': 'Test Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        # Scenario 2.1: Created budget is in draft state
        self.assertEqual(budget.state, 'draft')

        # Scenario 2.2: Test workflow transitions
        budget.action_budget_confirm()
        self.assertEqual(budget.state, 'confirm')

        budget.action_budget_validate()
        self.assertEqual(budget.state, 'validate')

        budget.action_budget_done()
        self.assertEqual(budget.state, 'done')

        # Scenario 2.3: Test cancellation and reset to draft
        budget.action_budget_cancel()
        self.assertEqual(budget.state, 'cancel')

        budget.action_budget_draft()
        self.assertEqual(budget.state, 'draft')

    def test_03_budget_lines_constraints(self):
        """Test constraints on budget lines (missing targets, dates outside budget)."""
        budget = self.budget_model.create({
            'name': 'Test Budget 2',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        budget_line_model = self.env['crossovered.budget.lines']

        # Scenario 3.1: Line without budget position and analytic account should fail
        with self.assertRaises(ValidationError):
            budget_line_model.create({
                'crossovered_budget_id': budget.id,
                'date_from': '2026-01-01',
                'date_to': '2026-12-31',
                'planned_amount': 1000,
            })

        # Create valid budget post
        budget_post = self.budget_post_model.create({
            'name': 'Valid Post for Lines',
            'account_ids': [(4, self.test_account.id)]
        })

        # Scenario 3.2: Dates outside budget period
        with self.assertRaises(ValidationError):
            budget_line_model.create({
                'crossovered_budget_id': budget.id,
                'general_budget_id': budget_post.id,
                'date_from': '2025-12-01',  # Before budget start
                'date_to': '2026-12-31',
                'planned_amount': 1000,
            })

        with self.assertRaises(ValidationError):
            budget_line_model.create({
                'crossovered_budget_id': budget.id,
                'general_budget_id': budget_post.id,
                'date_from': '2026-01-01',
                'date_to': '2027-01-31',  # After budget end
                'planned_amount': 1000,
            })

        # Scenario 3.3: Valid dates and targets should succeed
        line = budget_line_model.create({
            'crossovered_budget_id': budget.id,
            'general_budget_id': budget_post.id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'planned_amount': 1000,
        })
        self.assertTrue(line.id)

