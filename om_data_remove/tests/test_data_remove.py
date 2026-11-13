from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.om_data_remove.models import model

# The clearing deletes in the current transaction and never commits, so every test runs a real clearing and
# the test transaction rolls it back afterwards.

MASTER_MODELS = ['res.partner', 'res.company', 'res.users', 'res.currency', 'product.template', 'account.account',
                 'account.journal', 'account.tax', 'hr.employee', 'mrp.bom', 'project.project', 'stock.location',
                 'stock.warehouse', 'crm.team']


@tagged('post_install', '-at_install')
class TestDataRemove(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, 'data_remove_admin', groups='base.group_system')
        cls.employee = new_test_user(cls.env, 'data_remove_employee', groups='base.group_user')
        cls.Cleaning = cls.env['om.data.remove'].with_user(cls.admin)

    def _count(self, table):
        return self.Cleaning._om_count(table)

    def _master_counts(self):
        return {name: self.env[name].with_context(active_test=False).search_count([])
                for name in MASTER_MODELS if name in self.env}

    # -- access ------------------------------------------------------------

    def test_only_the_administrators_can_clear(self):
        Cleaning = self.env['om.data.remove'].with_user(self.employee)
        with self.assertRaises(AccessError):
            Cleaning._om_clear_all()
        with self.assertRaises(AccessError):
            Cleaning.action_open_clear()
        with self.assertRaises(AccessError):
            self.env['om.data.remove.report'].with_user(self.employee)._om_create_report(False)

    def test_nothing_is_deleted_without_the_confirmation_word(self):
        wizard = self.env['om.data.remove.wizard'].with_user(self.admin).create({'confirmation': 'yes'})
        before = {m._table: self._count(m._table) for _k, _l, m in self.Cleaning._om_models()}
        with self.assertRaises(UserError):
            wizard.action_remove()
        self.assertEqual(before, {table: self._count(table) for table in before})

    # -- the screen ------------------------------------------------------------

    def test_the_screen_counts_the_transactions_of_the_installed_applications(self):
        screen = self.Cleaning.create({})
        counts = self.Cleaning._om_counts()
        self.assertEqual(screen.total_count, sum(count for _k, _l, _m, count in counts))
        for _key, label, _model in self.Cleaning._om_models():
            self.assertIn(label, screen.summary)
        # an application that is not installed is not listed
        for _key, label, names in model.TRANSACTION_GROUPS:
            if not any(name in self.env for name in names):
                self.assertNotIn(label, screen.summary)

    def test_every_listed_model_is_a_real_table(self):
        for _key, _label, record in self.Cleaning._om_models():
            self.assertTrue(self.Cleaning._om_table_exists(record._table), record._name)

    # -- clearing --------------------------------------------------------------

    def test_clear_all_empties_the_transactions_and_keeps_the_master_data(self):
        partner = self.env['res.partner'].create({'name': 'Kept Partner'})
        has_mail = 'mail.message' in self.env
        if has_mail:
            partner.message_post(body='A note on a kept record')
        masters = self._master_counts()
        transactions = [m for _k, _l, m in self.Cleaning._om_models()]
        if not transactions:
            self.skipTest('no application with transactions is installed')
        before = sum(self._count(m._table) for m in transactions)

        wizard = self.env['om.data.remove.wizard'].with_user(self.admin).create({'confirmation': 'delete'})
        self.assertEqual(wizard.record_count, before)
        action = wizard.action_remove()

        report = self.env['om.data.remove.report'].browse(action['res_id'])
        self.assertTrue(report.cleared)
        self.assertFalse(report.blocked_count, report.outcome)
        for record in transactions:
            self.assertEqual(self._count(record._table), 0, record._name)
        self.assertEqual(self._master_counts(), masters)
        cleared_names = [m._name for m in transactions]
        if has_mail:
            # every message and activity goes, on the kept records too
            self.assertEqual(self._count('mail_message'), 0)
            self.assertEqual(self._count('mail_activity'), 0)
            self.assertTrue(partner.exists())
        self.assertFalse(self.env['ir.attachment'].search_count([('res_model', 'in', cleared_names)]))
        self.assertFalse(self.env['ir.model.data'].search_count([('model', 'in', cleared_names)]))

    def test_the_numbering_starts_again(self):
        sequence = self.env['ir.sequence'].create({
            'name': 'Sales test', 'code': 'sale.order', 'prefix': 'TST', 'number_next': 42, 'padding': 3,
        })
        other = self.env['ir.sequence'].create({'name': 'Not cleared', 'code': 'om.not.cleared', 'number_next': 42})
        self.Cleaning._om_clear_all()
        self.assertEqual(sequence.number_next_actual, 1)
        self.assertEqual(other.number_next_actual, 42)

    def test_a_table_the_database_refuses_to_empty_is_reported(self):
        # the currencies are referenced by the companies: the database refuses to delete them
        groups = [('test', 'Test', ['res.currency'])] + model.TRANSACTION_GROUPS
        with patch.object(model, 'TRANSACTION_GROUPS', groups):
            currencies = self._count('res_currency')
            result = self.Cleaning._om_clear_all()
            self.assertIn('res_currency', result['errors'])
            self.assertEqual(self._count('res_currency'), currencies)
            report = self.env['om.data.remove.report'].with_user(self.admin)._om_create_report(result)
        self.assertEqual(report.blocked_count, 1)
        self.assertIn('res_currency', report.outcome)
        line = report.line_ids.filtered(lambda l: l.table_name == 'res_currency')
        self.assertTrue(line.error)

    # -- the table report ------------------------------------------------------

    def test_the_report_lists_every_table_the_most_rows_first(self):
        report = self.env['om.data.remove.report'].with_user(self.admin)._om_create_report(False)
        self.assertFalse(report.cleared)
        self.env.cr.execute("SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")
        all_tables = self.env.cr.fetchone()[0]
        self.assertEqual(len(report.line_ids), all_tables)
        self.assertEqual(report.table_count + report.hidden_count, all_tables)
        lines = report.nonempty_line_ids
        # the framework, the configuration and the relation tables are not listed
        self.assertFalse(lines.filtered(lambda l: l.kind in ('framework', 'technical')))
        for table in ('ir_model', 'ir_model_fields', 'ir_ui_view', 'ir_ui_menu', 'ir_act_window', 'ir_attachment',
                      'ir_config_parameter', 'ir_cron', 'res_lang', 'res_country', 'res_groups'):
            self.assertNotIn(table, lines.mapped('table_name'), table)
            line = report.line_ids.filtered(lambda l, t=table: l.table_name == t)
            if line:
                self.assertEqual(line.kind, 'framework', table)
        self.assertEqual(lines.mapped('row_count'), sorted(lines.mapped('row_count'), reverse=True))
        self.assertTrue(all(lines.mapped('row_count')))
        partner_line = report.line_ids.filtered(lambda l: l.table_name == 'res_partner')
        self.assertEqual(partner_line.row_count, self._count('res_partner'))
        self.assertEqual(partner_line.kind, 'kept')
        self.assertEqual(partner_line.model, 'res.partner')
        if 'account.move' in self.env:
            self.assertEqual(report.line_ids.filtered(lambda l: l.table_name == 'account_move').kind, 'transaction')
        action = report.action_view_tables()
        self.assertEqual(action['domain'], [('report_id', '=', report.id)])

    def test_the_report_opens_from_the_screen(self):
        action = self.Cleaning.create({}).action_table_report()
        self.assertEqual(action['res_model'], 'om.data.remove.report')

    # -- emptying the tables that are left -------------------------------------

    def _report(self):
        return self.env['om.data.remove.report'].with_user(self.admin)._om_create_report(False)

    def _line(self, report, table):
        return report.line_ids.filtered(lambda l: l.table_name == table)

    def test_a_table_left_can_be_emptied(self):
        self.env['res.partner.category'].create({'name': 'Tag to delete'})
        report = self._report()
        line = self._line(report, 'res_partner_category')
        self.assertTrue(line.can_delete)
        action = line.with_user(self.admin).action_delete_rows()
        wizard = self.env['om.data.remove.table.wizard'].with_user(self.admin).with_context(action['context']).create({})
        self.assertEqual(wizard.record_count, self._count('res_partner_category'))
        with self.assertRaises(UserError):
            wizard.action_remove()
        wizard.confirmation = 'DELETE'
        result = wizard.action_remove()
        self.assertEqual(self._count('res_partner_category'), 0)
        after = self.env['om.data.remove.report'].browse(result['res_id'])
        self.assertEqual(after.action, 'tables')
        self.assertTrue(after.deleted_count)
        self.assertEqual(self._line(after, 'res_partner_category').row_count, 0)

    def test_the_framework_tables_are_never_offered(self):
        report = self._report()
        for table in ('res_users', 'res_company', 'ir_model', 'ir_attachment', 'res_groups', 'res_currency'):
            line = self._line(report, table)
            if line:
                self.assertFalse(line.can_delete, table)
        with self.assertRaises(UserError):
            self._line(report, 'res_users').with_user(self.admin).action_delete_rows()
        # a relation table goes with the records it links
        relation = report.line_ids.filtered(lambda l: l.kind == 'technical')[:1]
        self.assertFalse(relation.can_delete)

    def test_a_table_kept_records_still_need_is_reported(self):
        # the partners of the users and of the companies cannot go: the database refuses the whole statement
        report = self._report()
        line = self._line(report, 'res_partner')
        self.assertTrue(line.can_delete)
        partners = self._count('res_partner')
        wizard = self.env['om.data.remove.table.wizard'].with_user(self.admin).create(
            {'line_ids': [(6, 0, line.ids)], 'confirmation': 'DELETE'})
        after = self.env['om.data.remove.report'].browse(wizard.action_remove()['res_id'])
        self.assertEqual(self._count('res_partner'), partners)
        self.assertEqual(after.blocked_count, 1)
        self.assertIn('res_partner', after.outcome)
