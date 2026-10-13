import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

MODULE = 'om_account_asset'

# key: (name, words of the accounts of the category, months between two depreciations, number of depreciations)
CATEGORIES = {
    'computers': ('Computers', ('Technology', 'Computer', 'Equipment'), 1, 36),
    'vehicles': ('Vehicles', ('Vehicle',), 1, 60),
    'furniture': ('Office Furniture', ('Furniture',), 12, 10),
}
NOT_ACCUMULATED = ('Accumulated', 'Amortization', 'Depreciation')


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_asset_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_asset_demo_partner_id(self, xmlid):
        """ The id of a demo partner: given by its id, the field is not delayed by the loading of the demo
        partners of the other modules. """
        return (self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.partner']).id

    def _om_asset_demo_missing(self, data):
        """ The demo records not created yet: the existing ones are left as they are. """
        return {xmlid: values for xmlid, values in data.items() if not self.ref(xmlid, raise_if_not_found=False)}

    def _om_asset_demo_free_code(self, code, company):
        Account = self.env['account.account'].with_company(company)
        if not code:
            return None
        for step in range(1, 100):
            if code.isdigit():
                candidate = str(int(code) + step).zfill(len(code))
            else:
                candidate = f'{code}.{step}'
            if not Account.search_count([*Account._check_company_domain(company), ('code', '=', candidate)], limit=1):
                return candidate
        return False

    def _om_asset_demo_accounts(self, company):
        """ The accounts of the demo categories, by type and name in the chart of the company. An account
        missing in the chart is given by the xmlid of the demo account created for it.

        :return: {category key: (asset account, accumulated depreciation account, expense account)}
        """
        Account = self.env['account.account'].with_company(company)
        domain = Account._check_company_domain(company)

        def find_named(account_types, words, extra_domain=()):
            """ The first account of the types named with one of `words` """
            for word in words:
                account = Account.search([*domain, *extra_domain, ('account_type', 'in', account_types),
                                          ('name', 'ilike', word)], limit=1)
                if account:
                    return account
            return Account

        def find(account_types, words, extra_domain=()):
            """ The first account of the types named with one of `words`, else the first one of the types """
            return find_named(account_types, words, extra_domain) or Account.search(
                [*domain, *extra_domain, ('account_type', 'in', account_types)], limit=1)

        not_accumulated = [('name', 'not ilike', word) for word in NOT_ACCUMULATED]
        accumulated_domain = ['|', '|', *[('name', 'ilike', word) for word in NOT_ACCUMULATED]]
        accumulated_xmlid = self._om_asset_xmlid('om_asset_demo_accumulated_depreciation')
        expense_xmlid = self._om_asset_xmlid('om_asset_demo_depreciation_expense')
        result = {}
        for key, (_name, words, _period, _number) in CATEGORIES.items():
            asset = find(['asset_fixed'], words, not_accumulated) or find(['asset_non_current'], words)
            accumulated = (
                find(['asset_fixed'], words, accumulated_domain)
                or self.ref(accumulated_xmlid, raise_if_not_found=False)
                or accumulated_xmlid
            )
            expense = (
                find_named(['expense_depreciation'], words)
                or find_named(['expense_depreciation'], ['Tangible'], [('name', 'not ilike', 'Intangible')])
                or find(['expense_depreciation'], [])
                or find_named(['expense'], ['Depreciation'])
                or self.ref(expense_xmlid, raise_if_not_found=False)
                or expense_xmlid
            )
            result[key] = (asset, accumulated, expense)
        return result

    def _om_asset_demo_enabled(self):
        company = self.env.company
        return bool(company.chart_template) and not company.parent_id

    @template(model='account.account', demo=True)
    def _get_om_asset_demo_1_account(self, template_code):
        if not self._om_asset_demo_enabled():
            return {}
        company = self.env.company
        accounts = self._om_asset_demo_accounts(company)
        if not all(asset for asset, _accumulated, _expense in accounts.values()):
            return {}
        data = {}
        needed = {account for values in accounts.values() for account in values if isinstance(account, str)}
        if self._om_asset_xmlid('om_asset_demo_accumulated_depreciation') in needed:
            data[self._om_asset_xmlid('om_asset_demo_accumulated_depreciation')] = {
                'name': 'Accumulated Depreciation',
                'code': self._om_asset_demo_free_code(accounts['computers'][0].code, company),
                'account_type': 'asset_fixed',
            }
        if self._om_asset_xmlid('om_asset_demo_depreciation_expense') in needed:
            base_account = company.expense_account_id or self.env['account.account'].with_company(company).search([
                *self.env['account.account']._check_company_domain(company), ('account_type', '=', 'expense'),
            ], limit=1)
            data[self._om_asset_xmlid('om_asset_demo_depreciation_expense')] = {
                'name': 'Depreciation Expense',
                'code': self._om_asset_demo_free_code(base_account.code, company),
                'account_type': 'expense_depreciation',
            }
        for values in data.values():
            if values['code'] is None:
                # a chart without codes gets accounts without code
                del values['code']
            elif not values['code']:
                return {}
        return self._om_asset_demo_missing(data)

    @template(model='account.asset.category', demo=True)
    def _get_om_asset_demo_2_category(self, template_code):
        if not self._om_asset_demo_enabled():
            return {}
        company = self.env.company
        journal = self.ref('general', raise_if_not_found=False) or self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(company), ('type', '=', 'general')], limit=1)
        accounts = self._om_asset_demo_accounts(company)
        if not journal or not all(asset for asset, _accumulated, _expense in accounts.values()):
            return {}
        data = {}
        for key, (name, _words, period, number) in CATEGORIES.items():
            asset, accumulated, expense = accounts[key]
            data[self._om_asset_xmlid(f'om_asset_category_{key}')] = {
                'name': name,
                'company_id': company.id,
                'type': 'purchase',
                'journal_id': journal.id,
                'account_asset_id': asset.id,
                'account_depreciation_id': accumulated if isinstance(accumulated, str) else accumulated.id,
                'account_depreciation_expense_id': expense if isinstance(expense, str) else expense.id,
                'method': 'linear',
                'method_time': 'number',
                'method_number': number,
                'method_period': period,
                'date_first_depreciation': 'last_day_period',
                'prorata': key == 'vehicles',
                'open_asset': True,
            }
        return self._om_asset_demo_missing(data)

    @template(model='account.asset.asset', demo=True)
    def _get_om_asset_demo_3_asset(self, template_code):
        if not self._om_asset_demo_enabled():
            return {}
        company = self.env.company
        today = fields.Date.context_today(self)
        assets = {
            self._om_asset_xmlid('om_asset_laptops'): {
                'name': 'Laptops for the sales team',
                'code': 'IT-0012',
                'category_id': self._om_asset_xmlid('om_asset_category_computers'),
                'partner_id': self._om_asset_demo_partner_id('base.res_partner_4'),
                'value': 4800.0,
                'date': today + relativedelta(months=-14, day=1),
                'method_period': 1,
                'method_number': 36,
                'prorata': False,
            },
            self._om_asset_xmlid('om_asset_delivery_van'): {
                'name': 'Delivery van',
                'code': 'VEH-0003',
                'category_id': self._om_asset_xmlid('om_asset_category_vehicles'),
                'partner_id': self._om_asset_demo_partner_id('base.res_partner_12'),
                'value': 32000.0,
                'salvage_value': 5000.0,
                'date': today + relativedelta(months=-7, day=12),
                'method_period': 1,
                'method_number': 60,
                'prorata': True,
            },
            self._om_asset_xmlid('om_asset_office_furniture'): {
                'name': 'Meeting room furniture',
                'code': 'FUR-0021',
                'category_id': self._om_asset_xmlid('om_asset_category_furniture'),
                'partner_id': self._om_asset_demo_partner_id('base.res_partner_3'),
                'value': 8500.0,
                'date': today + relativedelta(years=-1, month=1, day=1),
                'method_period': 12,
                'method_number': 10,
                'prorata': False,
            },
        }
        for values in assets.values():
            values.update({
                'company_id': company.id,
                'currency_id': company.currency_id.id,
                'method': 'linear',
                'method_time': 'number',
                'date_first_depreciation': 'last_day_period',
            })
        return self._om_asset_demo_missing(assets)

    def _om_asset_demo_closed_until(self):
        """ The end of the closed periods of the company: its lock dates and its closed fiscal years, when the
        fiscal year module is installed. """
        company = self.env.company
        dates = [company.fiscalyear_lock_date, company.hard_lock_date]
        if 'account.fiscal.year' in self.env:
            dates += self.env['account.fiscal.year'].search([
                ('company_id', '=', company.id), ('state', '=', 'closed')]).mapped('date_to')
        dates = [date for date in dates if date]
        return max(dates) if dates else None

    def _om_asset_post_load_demo(self):
        """ Confirm the demo assets: their depreciation board is computed and the past entries posted.
        The depreciation of the closed periods is not posted but taken as opening depreciation. Called again
        on the companies already done, it changes nothing. """
        assets = self.env['account.asset.asset']
        for name in ('om_asset_laptops', 'om_asset_delivery_van', 'om_asset_office_furniture'):
            assets |= self.ref(self._om_asset_xmlid(name), raise_if_not_found=False) or assets
        assets = assets.filtered(lambda asset: asset.state == 'draft')
        if not assets:
            return
        closed_until = self._om_asset_demo_closed_until()
        try:
            with self.env.cr.savepoint():
                for asset in assets.filtered(lambda asset: closed_until and asset.date <= closed_until):
                    asset.compute_depreciation_board()
                    closed = asset.depreciation_move_ids.filtered(
                        lambda move: move.state == 'draft' and move.date <= closed_until)
                    if closed:
                        # recomputes the preview, without the entries of the closed periods
                        asset.opening_depreciation = sum(closed.mapped('asset_depreciation_amount'))
                assets.validate()
        except Exception:  # noqa: BLE001 the demo is not worth failing the installation
            _logger.exception('Error while confirming the demo assets of %s', self.env.company.name)

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_asset_post_load_demo()

    @api.model
    def _om_asset_post_load_demo_companies(self):
        for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
            self.with_company(company).with_context(allowed_company_ids=company.ids)._om_asset_post_load_demo()


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        # the demo data of the module is loaded on the companies with a chart when the module is set installed
        installing = len(self) == 1 and self.name == MODULE and self.state not in (
            'installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if installing and self.state == 'installed' and self.demo:
            self.env['account.chart.template'].sudo()._om_asset_post_load_demo_companies()
        return res
