from odoo import api, fields, models

# the Odoo account type of each predefined group of Tally
GROUP_ACCOUNT_TYPES = {
    'Branch / Divisions': 'liability_current',
    'Capital Account': 'equity',
    'Reserves & Surplus': 'equity',
    'Current Assets': 'asset_current',
    'Bank Accounts': 'asset_cash',
    'Cash-in-Hand': 'asset_cash',
    'Bank OD A/c': 'asset_cash',
    'Deposits (Asset)': 'asset_current',
    'Loans & Advances (Asset)': 'asset_current',
    'Stock-in-Hand': 'asset_current',
    'Sundry Debtors': 'asset_receivable',
    'Current Liabilities': 'liability_current',
    'Duties & Taxes': 'liability_current',
    'Provisions': 'liability_current',
    'Sundry Creditors': 'liability_payable',
    'Suspense A/c': 'liability_current',
    'Loans (Liability)': 'liability_non_current',
    'Secured Loans': 'liability_non_current',
    'Unsecured Loans': 'liability_non_current',
    'Fixed Assets': 'asset_fixed',
    'Investments': 'asset_non_current',
    'Misc. Expenses (ASSET)': 'asset_non_current',
    'Sales Accounts': 'income',
    'Direct Incomes': 'income',
    'Indirect Incomes': 'income_other',
    'Purchase Accounts': 'expense_direct_cost',
    'Direct Expenses': 'expense_direct_cost',
    'Indirect Expenses': 'expense',
}
NATURE_ACCOUNT_TYPES = {'asset': 'asset_current', 'liability': 'liability_current', 'income': 'income',
                        'expense': 'expense'}
ACTIONS = [('link', 'Link'), ('create', 'Create'), ('skip', 'Skip')]


def _account_types(self):
    return self.env['account.account']._fields['account_type'].selection


class OmTallyGroup(models.Model):
    _inherit = 'om.tally.group'

    account_type = fields.Selection(selection=_account_types, string='Odoo Account Type',
                                    compute='_compute_account_type', store=True, readonly=False, recursive=True,
                                    help="The type of the accounts made for the ledgers of this group.")

    @api.depends('primary_group', 'nature', 'parent_id.account_type', 'is_predefined')
    def _compute_account_type(self):
        for group in self:
            if group.is_predefined and group.primary_group in GROUP_ACCOUNT_TYPES:
                group.account_type = GROUP_ACCOUNT_TYPES[group.primary_group]
            elif group.parent_id.account_type:
                group.account_type = group.parent_id.account_type
            else:
                group.account_type = NATURE_ACCOUNT_TYPES.get(group.nature, 'asset_current')


class OmTallyLedger(models.Model):
    _inherit = 'om.tally.ledger'

    account_action = fields.Selection(ACTIONS, string='Account Action', default='create',
                                      help="Link: post to an account of the chart. Create: make a new account. "
                                           "Skip: leave the ledger out (its amounts go to the suspense account if "
                                           "you accept the difference).")
    account_id = fields.Many2one('account.account', string='Odoo Account', ondelete='set null',
                                 domain="[('company_ids', 'in', company_id)]")
    account_type = fields.Selection(selection=_account_types, string='New Account Type',
                                    compute='_compute_new_account', store=True, readonly=False)
    new_account_code = fields.Char(string='New Account Code')
    new_account_name = fields.Char(string='New Account Name', compute='_compute_new_account', store=True,
                                   readonly=False)
    match_note = fields.Char(string='Matched By', readonly=True)
    partner_action = fields.Selection(ACTIONS, string='Partner Action', default='create',
                                      help="Link: use the Odoo partner. Create: make a partner from the ledger. "
                                           "Skip: post to the fallback partner of the import.")
    partner_id = fields.Many2one('res.partner', string='Odoo Partner', ondelete='set null')
    partner_match_note = fields.Char(string='Partner Matched By', readonly=True)
    journal_action = fields.Selection(ACTIONS, string='Journal Action', default='create')
    journal_id = fields.Many2one('account.journal', string='Odoo Journal', ondelete='set null',
                                 domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]")
    tax_id = fields.Many2one('account.tax', string='Odoo Tax', ondelete='set null',
                             domain="[('company_id', '=', company_id)]",
                             help="The tax of Odoo this tax ledger stands for, used to rebuild invoices.")
    is_applied = fields.Boolean(string='Created & Linked', readonly=True, copy=False)

    @api.depends('group_id.account_type', 'name')
    def _compute_new_account(self):
        for ledger in self:
            ledger.account_type = ledger.group_id.account_type or 'asset_current'
            ledger.new_account_name = ledger.name

    def action_link(self):
        for ledger in self:
            if ledger.role in ('receivable', 'payable'):
                ledger.partner_action = 'link' if ledger.partner_id else ledger.partner_action
            elif ledger.account_id:
                ledger.account_action = 'link'
        return True

    def action_create(self):
        for ledger in self:
            if ledger.role in ('receivable', 'payable'):
                ledger.partner_action = 'create'
            else:
                ledger.account_action = 'create'
        return True

    def action_skip(self):
        for ledger in self:
            if ledger.role in ('receivable', 'payable'):
                ledger.partner_action = 'skip'
            else:
                ledger.account_action = 'skip'
        return True


class OmTallyVoucherType(models.Model):
    _inherit = 'om.tally.voucher.type'

    journal_id = fields.Many2one('account.journal', string='Odoo Journal', ondelete='set null',
                                 domain="[('company_id', '=', company_id)]",
                                 help="Empty: the journal is chosen from the kind of voucher.")


class OmTallyCostCategory(models.Model):
    _inherit = 'om.tally.cost.category'

    analytic_plan_id = fields.Many2one('account.analytic.plan', string='Analytic Plan', ondelete='set null')


class OmTallyCostCentre(models.Model):
    _inherit = 'om.tally.cost.centre'

    analytic_action = fields.Selection(ACTIONS, string='Analytic Action', default='create')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account',
                                          ondelete='set null')


class OmTallyVoucher(models.Model):
    _inherit = 'om.tally.voucher'

    move_id = fields.Many2one('account.move', string='Odoo Entry', ondelete='set null', readonly=True, copy=False)

    def action_open_move(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': self.move_id.id,
                'view_mode': 'form'}

    def action_retry(self):
        self.filtered(lambda v: v.state == 'error').write({'state': 'staged', 'error_message': False})
        imports = self.import_id.filtered(lambda i: i.state == 'done')
        imports.write({'state': 'posting'})
        imports._om_tally_trigger_posting()
        return True
