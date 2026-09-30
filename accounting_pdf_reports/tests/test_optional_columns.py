from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestOptionalColumns(AccountTestInvoicingCommon):
    """ A column for a feature the company does not use is a stripe of white space.

    Analytic accounting and several currencies are both features a company turns on, and
    turning one on is what puts its group on the base user group. The reports follow.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.analytic_group = cls.env.ref('analytic.group_analytic_accounting')
        cls.base_user = cls.env.ref('base.group_user')
        cls.reader = cls.env['res.users'].create({
            'name': 'Book Keeper', 'login': 'bookkeeper.columns',
            'groups_id': [Command.set([cls.base_user.id,
                                       cls.env.ref('account.group_account_manager').id])],
        })
        cls.entry = cls.init_invoice('out_invoice', amounts=[1000.0],
                                     invoice_date='2026-03-01', taxes=[], post=True)

    def _set_analytic(self, enabled):
        """ What the Analytic Accounting switch in the settings does. """
        command = Command.link if enabled else Command.unlink
        self.base_user.implied_ids = [command(self.analytic_group.id)]
        self.reader.groups_id = [command(self.analytic_group.id)]
        self.env.flush_all()
        self.env.invalidate_all()

    def _journal_entry_page(self):
        html, __ = self.env['ir.actions.report'].with_user(self.reader)._render_qweb_html(
            'accounting_pdf_reports.report_journal_entries', self.entry.ids)
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_the_analytic_column_follows_the_setting(self):
        self._set_analytic(False)
        self.assertFalse(self.reader.has_group('analytic.group_analytic_accounting'))
        self.assertNotIn('Analytic Distribution', self._journal_entry_page())

        self._set_analytic(True)
        self.assertIn('Analytic Distribution', self._journal_entry_page())

    def test_the_total_spans_the_columns_that_are_there(self):
        """ Without this the Debit and Credit of the total sit under the wrong headings. """
        self._set_analytic(False)
        self.assertIn('colspan="3"', self._journal_entry_page())

        self._set_analytic(True)
        self.assertIn('colspan="4"', self._journal_entry_page())
