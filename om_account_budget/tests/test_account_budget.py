from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestAccountBudget(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestAccountBudget, cls).setUpClass()
        cls.account_model = cls.env['account.account']
        cls.budget_post_model = cls.env['account.budget.post']
        
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

