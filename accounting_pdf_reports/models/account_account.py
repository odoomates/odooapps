from odoo import fields, models

CASH_FLOW_ACTIVITIES = [
    ('operating', 'Operating Activities'),
    ('investing', 'Investing Activities'),
    ('financing', 'Financing Activities'),
]

# Odoo 15 tells the accounts apart by their account type record: the finer kind of each type of the
# account module, under the names Odoo 16 gives them, for the reports that need more than the
# internal type and the internal group (the cash flow statement)
ACCOUNT_TYPE_KINDS = {
    'account.data_account_type_receivable': 'asset_receivable',
    'account.data_account_type_payable': 'liability_payable',
    'account.data_account_type_liquidity': 'asset_cash',
    'account.data_account_type_credit_card': 'liability_credit_card',
    'account.data_account_type_current_assets': 'asset_current',
    'account.data_account_type_non_current_assets': 'asset_non_current',
    'account.data_account_type_prepayments': 'asset_prepayments',
    'account.data_account_type_fixed_assets': 'asset_fixed',
    'account.data_account_type_current_liabilities': 'liability_current',
    'account.data_account_type_non_current_liabilities': 'liability_non_current',
    'account.data_account_type_equity': 'equity',
    'account.data_unaffected_earnings': 'equity_unaffected',
    'account.data_account_type_revenue': 'income',
    'account.data_account_type_other_income': 'income_other',
    'account.data_account_type_expenses': 'expense',
    'account.data_account_type_depreciation': 'expense_depreciation',
    'account.data_account_type_direct_costs': 'expense_direct_cost',
    'account.data_account_off_sheet': 'off_balance',
}
# the kind of the other account types, by internal group
INTERNAL_GROUP_KINDS = {
    'asset': 'asset_current',
    'liability': 'liability_current',
    'equity': 'equity',
    'income': 'income',
    'expense': 'expense',
    'off_balance': 'off_balance',
}


class AccountAccountType(models.Model):
    _inherit = 'account.account.type'

    def _get_om_kind(self):
        """ :return: the kind of this account type, under the name Odoo 16 gives it (e.g. 'asset_fixed') """
        self.ensure_one()
        for xmlid, kind in ACCOUNT_TYPE_KINDS.items():
            # env.ref is cached: no query for each account
            account_type = self.env.ref(xmlid, raise_if_not_found=False)
            if account_type and account_type.id == self.id:
                return kind
        if self.type == 'receivable':
            return 'asset_receivable'
        if self.type == 'payable':
            return 'liability_payable'
        if self.type == 'liquidity':
            return 'liability_credit_card' if self.internal_group == 'liability' else 'asset_cash'
        return INTERNAL_GROUP_KINDS.get(self.internal_group, 'off_balance')


class AccountAccount(models.Model):
    _inherit = 'account.account'

    cash_flow_activity = fields.Selection(
        CASH_FLOW_ACTIVITIES, string='Cash Flow Activity',
        help="Section of the Cash Flow Statement for the cash paid or received against this account. "
             "Leave empty to use the section of its type: fixed and non-current assets are investing, "
             "non-current liabilities and equity are financing, the others are operating.",
    )

    def _get_om_kind(self):
        """ :return: the kind of the type of this account, see account.account.type._get_om_kind() """
        self.ensure_one()
        return self.user_type_id._get_om_kind() if self.user_type_id else False
