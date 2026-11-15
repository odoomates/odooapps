from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmDynamicReportBook(models.AbstractModel):
    """Bank Book and Cash Book: the General Ledger of the accounts of the bank
    (cash) journals -- their own account and the outstanding receipts and
    payments accounts of their payment methods, as the PDF books of Daily
    Reports take them -- with the initial balance, every receipt and payment
    and the running balance."""
    _name = 'om.dynamic.report.book'
    _inherit = 'om.dynamic.report.general.ledger'
    _description = 'Dynamic Bank or Cash Book'

    _report_section = 'ledgers'
    # the base of the two books, not a report of its own: no name, so it stays out of the switcher
    _report_name = ''
    _odr_journal_type = False

    @api.model
    def _odr_book_journals(self):
        return self.env['account.journal'].search([
            ('type', '=', self._odr_journal_type), ('company_id', 'in', self._odr_company_ids())])

    @api.model
    def _odr_book_accounts(self):
        journals = self._odr_book_journals()
        accounts = journals.default_account_id
        accounts |= (journals.inbound_payment_method_line_ids | journals.outbound_payment_method_line_ids
                     ).payment_account_id
        return accounts

    @api.model
    def _om_filters(self):
        filters = self._odr_filters('account_ids', 'journal_ids', 'partner_ids')
        for spec in filters:
            if spec['key'] == 'account_ids':
                spec['domain'] = [('id', 'in', self._odr_book_accounts().ids)]
        return filters

    @api.model
    def _om_choices(self):
        choices = []
        for choice in super()._om_choices():
            if choice['key'] == 'display_account':
                # the accounts of the book only: with movements or with a balance
                choice = {**choice, 'choices': [c for c in choice['choices'] if c[0] != 'all']}
            choices.append(choice)
        return choices

    @api.model
    def _om_get_columns(self, options):
        columns = super()._om_get_columns(options)
        labels = {'debit': self.env._("Receipts"), 'credit': self.env._("Payments")}
        for column in columns:
            column['label'] = labels.get(column['key'], column['label'])
        return columns

    @api.model
    def _odr_domain(self, options, date_from=False, date_to=False, before=False):
        return super()._odr_domain(options, date_from, date_to, before) + [
            ('account_id', 'in', self._odr_book_accounts().ids)]


class OmDynamicReportBankBook(models.AbstractModel):
    _name = 'om.dynamic.report.bank.book'
    _inherit = 'om.dynamic.report.book'
    _description = 'Dynamic Bank Book'

    _report_name = 'Bank Book'
    _report_description = _lt("Every receipt and payment of the bank accounts, with the running balance.")
    _report_sequence = 22
    _report_icon = 'account_balance'
    _odr_journal_type = 'bank'

    @api.model
    def _om_report_title(self):
        return self.env._("Bank Book")


class OmDynamicReportCashBook(models.AbstractModel):
    _name = 'om.dynamic.report.cash.book'
    _inherit = 'om.dynamic.report.book'
    _description = 'Dynamic Cash Book'

    _report_name = 'Cash Book'
    _report_description = _lt("Every receipt and payment in cash, with the running balance.")
    _report_sequence = 23
    _report_icon = 'payments'
    _odr_journal_type = 'cash'

    @api.model
    def _om_report_title(self):
        return self.env._("Cash Book")
