from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# name, method, number of months, months between two entries
STANDARD_CATEGORIES = [
    ('buildings', _lt('Buildings'), 'linear', 300, 12),
    ('furniture', _lt('Furniture and Fixtures'), 'linear', 120, 12),
    ('vehicles', _lt('Vehicles'), 'linear', 60, 1),
    ('machinery', _lt('Machinery and Equipment'), 'linear', 84, 1),
    ('computers', _lt('Computer Equipment'), 'linear', 36, 1),
    ('land', _lt('Land'), 'none', 12, 12),
]


class AssetStandardCategories(models.TransientModel):
    """ The usual asset categories, ready to use: the accounts and the journal are chosen once for all. """
    _name = 'asset.standard.categories'
    _description = 'Create the Standard Asset Categories'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, check_company=True,
                                 domain="[('type', '=', 'general')]",
                                 default=lambda self: self._default_account_or_journal('journal'))
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account', required=True, check_company=True,
        default=lambda self: self._default_account_or_journal('asset'),
        help='Where the gross value of the assets is booked.')
    account_depreciation_id = fields.Many2one(
        'account.account', string='Accumulated Depreciation Account', required=True, check_company=True,
        default=lambda self: self._default_account_or_journal('depreciation'))
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Depreciation Expense Account', required=True, check_company=True,
        default=lambda self: self._default_account_or_journal('expense'))
    buildings = fields.Boolean(string='Buildings (25 years)', default=True)
    furniture = fields.Boolean(string='Furniture and Fixtures (10 years)', default=True)
    vehicles = fields.Boolean(string='Vehicles (5 years)', default=True)
    machinery = fields.Boolean(string='Machinery and Equipment (7 years)', default=True)
    computers = fields.Boolean(string='Computer Equipment (3 years)', default=True)
    land = fields.Boolean(string='Land (no depreciation)', default=True)

    @api.model
    def _default_account_or_journal(self, kind):
        company = self.env.company
        Account = self.env['account.account']
        company_domain = [('company_ids', 'in', company.id)]
        if kind == 'journal':
            return self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        if kind == 'asset':
            return Account.search(company_domain + [('account_type', '=', 'asset_fixed')], limit=1)
        if kind == 'depreciation':
            return Account.search(company_domain + [('account_type', '=', 'asset_fixed'),
                                                    ('name', 'ilike', 'depreciation')], limit=1) \
                or Account.search(company_domain + [('account_type', '=', 'asset_fixed')], limit=1)
        return Account.search(company_domain + [('account_type', '=', 'expense_depreciation')], limit=1) \
            or Account.search(company_domain + [('account_type', '=', 'expense')], limit=1)

    def action_create(self):
        self.ensure_one()
        Category = self.env['account.asset.category']
        existing = set(Category.with_context(active_test=False).search(
            [('company_id', '=', self.company_id.id)]).mapped('name'))
        created = Category
        for key, name, method, months, period in STANDARD_CATEGORIES:
            name = str(name)
            if not self[key] or name in existing:
                continue
            created |= Category.create({
                'name': name,
                'company_id': self.company_id.id,
                'type': 'purchase',
                'journal_id': self.journal_id.id,
                'account_asset_id': self.account_asset_id.id,
                'account_depreciation_id': self.account_depreciation_id.id,
                'account_depreciation_expense_id': self.account_depreciation_expense_id.id,
                'method': method,
                'method_time': 'number',
                'method_number': max(months // period, 1),
                'method_period': period,
                'prorata': method != 'none',
                'date_first_depreciation': 'last_day_period',
            })
        if not created:
            raise UserError(_('These categories exist already.'))
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_asset.action_account_asset_asset_list_normal_purchase')
        action['domain'] = [('id', 'in', created.ids)]
        return action
