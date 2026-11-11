from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountantBundle(TransactionCase):
    """What the bundle itself adds on top of the modules it installs."""

    def test_the_bundle_installs_the_accounting_modules(self):
        expected = {
            'accounting_pdf_reports', 'om_account_asset', 'om_account_budget', 'om_fiscal_year',
            'om_recurring_payments', 'om_account_daily_reports', 'om_account_followup', 'om_account_reconcile',
            'om_account_cash_forecast', 'om_account_check_printing', 'om_currency_rate_update',
        }
        installed = set(self.env['ir.module.module'].search([
            ('name', 'in', list(expected)), ('state', '=', 'installed'),
        ]).mapped('name'))
        self.assertEqual(installed, expected)

    def test_the_accounting_groups_are_renamed(self):
        self.assertEqual(self.env.ref('account.group_account_user').name, 'Accountant')
        self.assertEqual(self.env.ref('account.group_account_manager').name, 'Advisor')
        self.assertEqual(self.env.ref('account.group_account_readonly').name, 'Auditor')
        # an advisor is an accountant, which the standard groups do not say
        self.assertIn(self.env.ref('account.group_account_user'),
                      self.env.ref('account.group_account_manager').implied_ids)

    def test_the_reconcile_action_is_on_the_journal_items(self):
        action = self.env.ref('om_account_accountant.action_account_reconciliation')
        self.assertEqual(action.name, 'Reconcile')
        self.assertEqual(action.model_id.model, 'account.move.line')
        self.assertEqual(action.binding_model_id.model, 'account.move.line')

    def test_invoices_can_be_in_payment(self):
        self.assertEqual(self.env['account.move']._get_invoice_in_payment_state(), 'in_payment')

    def test_anglo_saxon_accounting_is_offered_in_the_settings(self):
        settings = self.env['res.config.settings'].create({})
        self.assertIn('anglo_saxon_accounting', settings._fields)
        settings.anglo_saxon_accounting = True
        settings.execute()
        self.assertTrue(self.env.company.anglo_saxon_accounting)
