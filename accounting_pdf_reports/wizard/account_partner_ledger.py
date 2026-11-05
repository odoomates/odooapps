from odoo import fields, models, api, _


class AccountPartnerLedger(models.TransientModel):
    _name = "account.report.partner.ledger"
    _inherit = "account.common.partner.report"
    _description = "Account Partner Ledger"

    amount_currency = fields.Boolean("With Currency",
                                     help="It adds the currency column on "
                                          "report if the currency differs from "
                                          "the company currency.")
    reconciled = fields.Boolean(
        'Reconciled Entries', default=True,
        help='Also lists the entries that are fully reconciled today. Untick it for the open items only: an invoice '
             'paid since then is left out, so the balance of a past date can look lower than it was.'
    )
    initial_balance = fields.Boolean(
        string='Include Initial Balances', default=True,
        help='With a start date, a row shows the balance of each partner before it, and the running balance starts '
             'from it. A partner without entries in the period is still listed when this balance is not zero.'
    )

    def _get_report_data(self, data):
        data = self.pre_print_report(data)
        data['form'].update({'reconciled': self.reconciled,
                             'amount_currency': self.amount_currency,
                             'initial_balance': self.initial_balance})
        return data

    def _print_report(self, data):
        data = self._get_report_data(data)
        return self.env.ref('accounting_pdf_reports.action_report_partnerledger').with_context(landscape=True).\
            report_action(self, data=data)
