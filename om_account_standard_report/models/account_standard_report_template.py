# -*- coding: utf-8 -*-

from odoo import api, models, fields, _


class AccountStandardLedger(models.Model):
    _name = 'account.report.template'
    _description = 'Account Standard Ledger Template'

    name = fields.Char(default='Standard Report Template')
    ledger_type = fields.Selection(
        [('general', 'General Ledger'),
         ('partner', 'Partner Ledger'),
         ('journal', 'Journal Ledger'),
         ('open', 'Open Ledger'),
         ('aged', 'Aged Balance'),
         ('analytic', 'Analytic Ledger')],
        string='Type', default='general', required=True,
        help=' * General Ledger : Journal entries group by account\n'
        ' * Partner Leger : Journal entries group by partner, with only payable/recevable accounts\n'
        ' * Journal Ledger : Journal entries group by journal, without initial balance\n'
        ' * Open Ledger : Openning journal at Start date\n')
    summary = fields.Boolean('Trial Balance', default=False,
                             help=' * Check : generate a trial balance.\n'
                             ' * Uncheck : detail report.\n')
    amount_currency = fields.Boolean('With Currency', help='It adds the currency column on report if the '
                                     'currency differs from the company currency.')
    reconciled = fields.Boolean(
        'With Reconciled Entries', default=True,
        help='Only for entrie with a payable/receivable account.\n'
        ' * Check this box to see un-reconcillied and reconciled entries with payable.\n'
        ' * Uncheck to see only un-reconcillied entries. Can be use only with parnter ledger.\n')
    partner_select_ids = fields.Many2many(
        comodel_name='res.partner', string='Partners',
        domain=['|', ('is_company', '=', True), ('parent_id', '=', False)],
        help='If empty, get all partners')
    account_method = fields.Selection([('include', 'Include'), ('exclude', 'Exclude')], string="Method")
    account_in_ex_clude_ids = fields.Many2many(comodel_name='account.account', string='Accounts',
                                               help='If empty, get all accounts')
    account_group_ids = fields.Many2many(comodel_name='account.group', string='Accounts Group')
    analytic_account_ids = fields.Many2many(comodel_name='account.analytic.account', string='Analytic Accounts')
    init_balance_history = fields.Boolean(
        'Initial balance with history.', default=True,
        help=' * Check this box if you need to report all the debit and the credit sum before the Start Date.\n'
        ' * Uncheck this box to report only the balance before the Start Date\n')
    company_id = fields.Many2one('res.company', string='Company', readonly=True,
                                 default=lambda self: self.env.user.company_id)
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id',
                                          string="Company Currency", readonly=True,
                                          help='Utility field to express amount currency', store=True)
    journal_ids = fields.Many2many('account.journal', string='Journals', required=True,
                                   default=lambda self: self.env['account.journal'].search(
                                       [('company_id', '=', self.env.user.company_id.id)]),
                                   help='Select journal, for the Open Ledger you need to set all journals.')
    date_from = fields.Date(string='Start Date', help='Use to compute initial balance.')
    date_to = fields.Date(string='End Date', help='Use to compute the entrie matched with futur.')
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries'),
                                    ], string='Target Moves', required=True, default='posted')
    result_selection = fields.Selection([('customer', 'Customers'),
                                         ('supplier', 'Suppliers'),
                                         ('customer_supplier', 'Customers and Suppliers')
                                         ], string="Partners Selection", required=True, default='supplier')
    report_name = fields.Char('Report Name')
    compact_account = fields.Boolean('Compact Account.	', default=False)

    @api.onchange('account_in_ex_clude_ids')
    def _onchange_account_in_ex_clude_ids(self):
        if self.account_in_ex_clude_ids:
            self.account_method = 'include'
        else:
            self.account_method = False

    @api.onchange('ledger_type')
    def _onchange_ledger_type(self):
        if self.ledger_type in ('partner', 'journal', 'open', 'aged'):
            self.compact_account = False
        if self.ledger_type == 'aged':
            self.date_from = False
            self.reconciled = False
        if self.ledger_type not in ('partner', 'aged',):
            self.reconciled = True
            return {'domain': {'account_in_ex_clude_ids': []}}
        self.account_in_ex_clude_ids = False
        if self.result_selection == 'supplier':
            return {'domain': {'account_in_ex_clude_ids': [('type_third_parties', '=', 'supplier')]}}
        if self.result_selection == 'customer':
            return {'domain': {'account_in_ex_clude_ids': [('type_third_parties', '=', 'customer')]}}
        return {'domain': {'account_in_ex_clude_ids': [('type_third_parties', 'in', ('supplier', 'customer'))]}}
