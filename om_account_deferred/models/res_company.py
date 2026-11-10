from odoo import fields, models

METHODS = [
    ('month', 'By Months'),
    ('day', 'By Days'),
    ('full_month', 'By Full Months'),
]
METHOD_HELP = ("How an amount is split across the periods it spans.\n"
               "By Months: every month counts as 30 days, and a part of a month for its days in it.\n"
               "By Days: each period for its number of days.\n"
               "By Full Months: only the whole months between the two dates count, equally.")
PERIODICITIES = [('month', 'Monthly'), ('year', 'Yearly')]
PERIODICITY_HELP = "Monthly: an entry at the end of each month. Yearly: an entry at the end of each fiscal year."


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_deferred_expense_journal_id = fields.Many2one(
        'account.journal', string='Deferred Expense Journal', domain="[('type', '=', 'general')]",
        help="Journal the deferral entries of the vendor bills are posted in.")
    om_deferred_expense_account_id = fields.Many2one(
        'account.account', string='Deferred Expense Account', domain="[('active', '=', True)]",
        help="Balance sheet account holding costs that have been paid but not yet incurred. Usually a prepaid "
             "expenses account.")
    om_deferred_expense_method = fields.Selection(
        METHODS, string='Deferred Expense Based on', default='month', required=True, help=METHOD_HELP)
    om_deferred_expense_generation = fields.Selection(
        [('on_post', 'On bill validation'), ('manual', 'Manually & Grouped')],
        string='Generate Deferred Expense Entries', default='on_post', required=True,
        help="On bill validation: the deferral entries of a bill are created when it is posted.\nManually & "
             "Grouped: one entry per period for all the deferred bills, generated from the Deferred Expense "
             "report and reversed on the first day of the next period.")
    om_deferred_expense_periodicity = fields.Selection(
        PERIODICITIES, string='Deferred Expense Periodicity', default='month', required=True,
        help=PERIODICITY_HELP)

    om_deferred_revenue_journal_id = fields.Many2one(
        'account.journal', string='Deferred Revenue Journal', domain="[('type', '=', 'general')]",
        help="Journal the deferral entries of the customer invoices are posted in.")
    om_deferred_revenue_account_id = fields.Many2one(
        'account.account', string='Deferred Revenue Account', domain="[('active', '=', True)]",
        help="Balance sheet account holding income that has been invoiced but not yet earned. Usually a "
             "deferred income liability account.")
    om_deferred_revenue_method = fields.Selection(
        METHODS, string='Deferred Revenue Based on', default='month', required=True, help=METHOD_HELP)
    om_deferred_revenue_generation = fields.Selection(
        [('on_post', 'On invoice validation'), ('manual', 'Manually & Grouped')],
        string='Generate Deferred Revenue Entries', default='on_post', required=True,
        help="On invoice validation: the deferral entries of an invoice are created when it is posted.\n"
             "Manually & Grouped: one entry per period for all the deferred invoices, generated from the "
             "Deferred Revenue report and reversed on the first day of the next period.")
    om_deferred_revenue_periodicity = fields.Selection(
        PERIODICITIES, string='Deferred Revenue Periodicity', default='month', required=True,
        help=PERIODICITY_HELP)

    def _om_deferred_settings(self, kind):
        """ The settings of one side: kind is 'expense' or 'revenue'. """
        self.ensure_one()
        prefix = 'om_deferred_%s_' % kind
        return {key: self[prefix + key] for key in ('journal_id', 'account_id', 'method', 'generation', 'periodicity')}
