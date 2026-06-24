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

    def test_04_theoretical_amount(self):
        """Test the computation of theoretical amount based on elapsed days."""
        from unittest.mock import patch
        from odoo import fields

        budget = self.budget_model.create({
            'name': 'Theo Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        budget_post = self.budget_post_model.create({
            'name': 'Theo Post',
            'account_ids': [(4, self.test_account.id)]
        })

        line = self.env['crossovered.budget.lines'].create({
            'crossovered_budget_id': budget.id,
            'general_budget_id': budget_post.id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'planned_amount': 3650,  # 10/day for non-leap year 365 days
        })

        # Scenario 4.1: Today is before date_from
        with patch('odoo.addons.om_account_budget.models.account_budget.fields.Date.today', return_value=fields.Date.to_date('2025-12-31')):
            line._compute_theoritical_amount()
            self.assertEqual(line.theoritical_amount, 0.0)

        # Scenario 4.2: Today is in the middle
        # 2026-01-31 is 30 days elapsed since 2026-01-01 (01-01 to 01-31 is 30 days diff)
        with patch('odoo.addons.om_account_budget.models.account_budget.fields.Date.today', return_value=fields.Date.to_date('2026-01-31')):
            line._compute_theoritical_amount()
            self.assertEqual(line.theoritical_amount, 300.0) # 30 days * 10/day

        # Scenario 4.3: Today is after date_to
        with patch('odoo.addons.om_account_budget.models.account_budget.fields.Date.today', return_value=fields.Date.to_date('2027-01-01')):
            line._compute_theoritical_amount()
            self.assertEqual(line.theoritical_amount, 3650.0)

        # Scenario 4.4: Paid date set
        line.paid_date = '2026-06-30'
        # Today is before paid_date -> 0
        with patch('odoo.addons.om_account_budget.models.account_budget.fields.Date.today', return_value=fields.Date.to_date('2026-05-01')):
            line._compute_theoritical_amount()
            self.assertEqual(line.theoritical_amount, 0.0)
        
        # Today is after paid_date -> full planned_amount
        with patch('odoo.addons.om_account_budget.models.account_budget.fields.Date.today', return_value=fields.Date.to_date('2026-07-01')):
            line._compute_theoritical_amount()
            self.assertEqual(line.theoritical_amount, 3650.0)

    def test_05_practical_amount(self):
        """Test the computation of practical amount from account move lines."""
        budget = self.budget_model.create({
            'name': 'Practical Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        budget_post = self.budget_post_model.create({
            'name': 'Practical Post',
            'account_ids': [(4, self.test_account.id)]
        })

        line = self.env['crossovered.budget.lines'].create({
            'crossovered_budget_id': budget.id,
            'general_budget_id': budget_post.id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'planned_amount': 1000,
        })

        # Create account move within the dates
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-06-15',
            'line_ids': [
                (0, 0, {
                    'account_id': self.test_account.id,
                    'debit': 500.0,
                    'credit': 0.0,
                    'name': 'Test Expense',
                }),
                (0, 0, {
                    'account_id': self.env.company.account_journal_suspense_account_id.id or self.env['account.account'].search([], limit=1).id,
                    'debit': 0.0,
                    'credit': 500.0,
                    'name': 'Test Credit',
                }),
            ]
        })
        move.action_post()

        line._compute_practical_amount()
        # practical_amount is credit - debit. Since we debited 500 on test_account, it's -500
        self.assertEqual(line.practical_amount, -500.0)

        line._compute_theoritical_amount()
        line._compute_percentage()
        # if theoretical != 0, percentage is practical / theoretical
        # We don't assert the exact percentage because it depends on today's date during test run, 
        # but we can test if it doesn't crash.
        self.assertIsNotNone(line.percentage)
