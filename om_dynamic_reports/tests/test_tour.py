from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestDynamicReportsTour(AccountTestInvoicingCommon, HttpCase):
    """ The screen only exists in the browser: open a ledger, unfold an account,
    switch to the trial balance and change an option. """

    def test_tour(self):
        admin = self.env.ref('base.user_admin')
        admin.groups_id |= self.env.ref('account.group_account_readonly')
        # the invoice is in the company of the test, which is not the main one when the main company already has
        # a chart of accounts
        company = self.company_data['company']
        admin.write({'company_ids': [Command.link(company.id)], 'company_id': company.id})
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], post=True,
                          invoice_date=__import__('odoo').fields.Date.today())
        action = self.env.ref('om_dynamic_reports.action_general_ledger')
        self.start_tour('/odoo/action-%s' % action.id, 'om_dynamic_reports_tour', login='admin', timeout=120)
