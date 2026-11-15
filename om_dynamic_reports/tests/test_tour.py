from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestDynamicReportsTour(AccountTestInvoicingCommon, HttpCase):
    """ The screen only exists in the browser: open a ledger, unfold an account,
    switch to the trial balance and change an option. """

    def test_tour(self):
        self.env.ref('base.user_admin').group_ids |= self.env.ref('account.group_account_readonly')
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], post=True,
                          invoice_date=__import__('odoo').fields.Date.today())
        action = self.env.ref('om_dynamic_reports.action_general_ledger')
        self.start_tour('/odoo/action-%s' % action.id, 'om_dynamic_reports_tour', login='admin', timeout=120)
