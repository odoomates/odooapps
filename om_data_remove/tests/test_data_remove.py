from unittest import SkipTest
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.modules.registry import Registry
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tests.common import get_db_name

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.om_data_remove.models import model

# This module deletes with raw SQL and commits at once: TestDataRemove removes nothing, the other classes patch the
# commit so that the deletions stay in the test transaction.


@tagged('post_install', '-at_install')
class TestDataRemove(TransactionCase):

    def setUp(self):
        super().setUp()
        self.settings = self.env['res.config.settings'].create({})

    def test_only_the_settings_administrators_may_remove(self):
        user = new_test_user(self.env, login='data_remove_user', groups='base.group_user')
        as_user = self.settings.with_user(user)
        self.assertFalse(as_user._remove_sales())
        self.assertFalse(as_user._remove_data(['res.partner']))
        # nothing was deleted
        self.assertTrue(self.env['res.partner'].search_count([]))

    def test_an_unknown_model_is_skipped(self):
        # a model that is not installed must not stop the removal, and must not delete anything either
        self.assertTrue(self.settings._remove_data(['no.such.model.here']))
        self.assertTrue(self.env['res.partner'].search_count([]))

    def test_the_sequences_are_reset(self):
        sequence = self.env['ir.sequence'].create({
            'name': 'Data Remove Test', 'code': 'data.remove.test', 'prefix': 'DRT/', 'number_next': 42,
        })
        self.assertTrue(self.settings._remove_data([], ['DRT']))
        self.assertEqual(sequence.number_next, 1)

    def test_every_button_of_the_wizard_exists(self):
        for name in ('_remove_sales', '_remove_product', '_remove_data'):
            self.assertTrue(callable(getattr(self.settings, name, None)), name)

    def test_the_screen_counts_and_asks_for_confirmation(self):
        from unittest.mock import patch
        from odoo.addons.om_data_remove.models import model
        # a table present on every database stands for the messages
        patcher = patch.dict(model.REMOVAL_MODELS, {'message': ['res.partner']})
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = self.env['res.config.settings'].create({})
        self.assertEqual(settings.om_remove_count_message, settings._om_removal_count('message'))
        self.assertGreater(settings.om_remove_count_message, 0)
        self.assertGreaterEqual(settings.om_remove_count_all, settings.om_remove_count_message)

        action = settings.with_context(om_removal='message').action_om_open_removal()
        wizard = self.env[action['res_model']].with_context(action['context']).create({})
        self.assertEqual(wizard.record_count, settings.om_remove_count_message)
        self.assertIn('Contact', wizard.model_names)
        # nothing is deleted without the confirmation word, and nothing is deleted here at all
        with patch.object(type(settings), 'action_remove_message') as remove:
            wizard.confirmation = 'yes'
            with self.assertRaises(UserError):
                wizard.action_remove()
            remove.assert_not_called()
            wizard.confirmation = ' delete '
            wizard.action_remove()
            remove.assert_called_once()

        user = new_test_user(self.env, login='data_remove_viewer', groups='base.group_user')
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_remove()


@tagged('post_install', '-at_install')
class TestDataRemoveActions(TransactionCase):

    def setUp(self):
        super().setUp()
        commit_patcher = patch.object(self.env.cr, 'commit')
        commit_patcher.start()
        self.addCleanup(commit_patcher.stop)

    def _removal_wizard(self, key, user=None):
        settings = self.env['res.config.settings'].with_user(user or self.env.user)
        action = settings.create({}).with_context(om_removal=key).action_om_open_removal()
        return settings.env[action['res_model']].with_context(action['context']).create({})

    def test_the_wizard_deletes_the_chosen_tables_and_keeps_the_rest(self):
        # a base table stands for the product attributes, which may not be installed
        self.enterContext(patch.dict(model.REMOVAL_MODELS, {'product_attribute': ['res.partner.industry']}))
        industry = self.env['res.partner.industry'].create({'name': 'Data Remove Industry'})
        archived = self.env['res.partner.industry'].create({'name': 'Archived Industry', 'active': False})
        partner = self.env['res.partner'].create({'name': 'Data Remove Partner', 'industry_id': industry.id})
        wizard = self._removal_wizard('product_attribute')
        self.assertEqual(wizard.record_count,
                         self.env['res.partner.industry'].with_context(active_test=False).search_count([]))

        wizard.confirmation = 'DELETE'
        action = wizard.action_remove()
        self.assertEqual(action['params']['type'], 'success')
        self.env.invalidate_all()
        self.assertFalse(industry.exists())
        self.assertFalse(archived.exists())
        self.assertTrue(partner.exists())
        self.assertFalse(partner.industry_id)
        self.assertEqual(self._removal_wizard('product_attribute').record_count, 0)

    def test_a_removal_resets_only_its_own_sequences(self):
        self.enterContext(patch.dict(model.REMOVAL_MODELS, {'sales': [], 'purchase': []}))
        Sequence = self.env['ir.sequence']
        sale_by_code = Sequence.create({'name': 'Sale', 'code': 'sale.remove.test', 'number_next': 7})
        sale_by_prefix = Sequence.create({'name': 'Sale prefix', 'prefix': 'SALE/', 'number_next': 8})
        purchase = Sequence.create({'name': 'Purchase', 'code': 'purchase.remove.test', 'number_next': 9})
        other = Sequence.create({'name': 'Other', 'code': 'other.remove.test', 'prefix': 'OT/', 'number_next': 10})
        settings = self.env['res.config.settings'].create({})

        settings.action_remove_sales()
        self.assertEqual((sale_by_code.number_next, sale_by_prefix.number_next), (1, 1))
        self.assertEqual((purchase.number_next, other.number_next), (9, 10))
        settings.action_remove_purchase()
        self.assertEqual((purchase.number_next, other.number_next), (1, 10))

    def test_delete_all_keeps_the_master_data(self):
        settings = self.env['res.config.settings'].create({})
        removals = settings._om_removal_models('all')
        self.assertTrue(all(name in self.env for name in removals), 'the uninstalled models are left out')
        for kept in ('product.product', 'product.template', 'product.attribute', 'res.partner', 'res.users',
                     'res.company'):
            self.assertNotIn(kept, removals)

        with patch.object(type(settings), '_remove_data', autospec=True, return_value=True) as remove:
            self.assertTrue(settings._remove_all())
        removed = {name for call in remove.call_args_list for name in call.args[1]}
        expected = {name for group in model.ALL_GROUPS for name in model.REMOVAL_MODELS[group]}
        self.assertEqual(removed, expected)
        self.assertFalse(removed & set(model.REMOVAL_MODELS['product'] + model.REMOVAL_MODELS['product_attribute']))

    def test_only_the_administrators_reach_the_removals(self):
        self.enterContext(patch.dict(model.REMOVAL_MODELS, {'message': ['res.partner']}))
        rights_manager = new_test_user(self.env, login='data_remove_rights', groups='base.group_erp_manager')
        admin = new_test_user(self.env, login='data_remove_admin', groups='base.group_system')

        # the screen and the confirmation are for the settings administrators only
        with self.assertRaises(AccessError):
            self.env['res.config.settings'].with_user(rights_manager).create({})
        with self.assertRaises(AccessError):
            self.env['om.data.remove.wizard'].with_user(rights_manager).create({'removal': 'message'})
        self.assertEqual(self.env['res.config.settings'].with_user(rights_manager).new({}).om_remove_count_message, 0)

        # none of the buttons deletes anything for somebody else
        settings = self.env['res.config.settings'].create({}).with_user(rights_manager)
        with patch.object(type(settings), '_remove_data', autospec=True) as remove:
            for key, _section, _label in model.REMOVAL_GROUPS:
                getattr(settings, 'action_remove_%s' % key)()
            self.assertFalse(settings._remove_all())
            remove.assert_not_called()

        # a settings administrator sees the counts and deletes
        wizard = self._removal_wizard('message', user=admin)
        self.assertGreater(wizard.record_count, 0)
        wizard.confirmation = 'delete'
        with patch.object(type(self.env['res.config.settings']), 'action_remove_message') as remove:
            wizard.action_remove()
            remove.assert_called_once()


@tagged('post_install', '-at_install')
class TestDataRemoveAccounting(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        if 'account.move' not in Registry(get_db_name()):
            raise SkipTest('the accounting is not installed')
        super().setUpClass()

    def _new_statement(self):
        journal = self.company_data['default_journal_bank']
        return self.env['account.bank.statement'].create({
            'name': 'Week 7',
            'line_ids': [Command.create({
                'journal_id': journal.id, 'date': '2026-02-12', 'payment_ref': 'Deposit', 'amount': 250.0,
            })],
        })

    def test_removal_recomputes_the_bank_statement_balances(self):
        statement = self._new_statement()
        self.assertEqual(statement.balance_end, 250.0)
        # the lines are deleted in SQL, as the removals do
        self.env.cr.execute('DELETE FROM account_bank_statement_line')
        self.env['res.config.settings']._recompute_bank_statement_balances()
        self.assertEqual(statement.balance_end, 0.0)
        self.assertFalse(statement.line_ids)

    def test_account_removal_deletes_the_entries_and_keeps_the_setup(self):
        statement = self._new_statement()
        invoice = self.init_invoice('out_invoice', amounts=[100.0], invoice_date='2026-02-10', post=True)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': '2026-02-11'})._create_payments()
        self.assertTrue(invoice.matched_payment_ids or invoice.line_ids.matched_credit_ids)
        kept_records = [(record._name, record.id) for record in (
            self.partner_a, self.company_data['default_account_revenue'], self.company_data['default_journal_sale'],
            self.company_data['default_tax_sale'], self.product_a)]

        with patch.object(self.env.cr, 'commit'):
            wizard = self.env['res.config.settings'].create({}).with_context(
                om_removal='account').action_om_open_removal()
            wizard = self.env['om.data.remove.wizard'].with_context(wizard['context']).create({})
            self.assertGreaterEqual(wizard.record_count, 4)  # the invoice, the payment and their lines at least
            wizard.confirmation = 'DELETE'
            wizard.action_remove()
        self.env.invalidate_all()

        self.assertFalse(statement.exists())
        for name in ('account.move', 'account.move.line', 'account.payment', 'account.partial.reconcile'):
            self.assertFalse(self.env[name].sudo().with_context(active_test=False).search_count([]), name)
        for name, record_id in kept_records:
            self.assertTrue(self.env[name].browse(record_id).exists(), name)
