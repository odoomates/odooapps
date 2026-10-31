from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.om_account_loan.models.account_loan import ONE_DAY, add_months


class AccountLoan(models.Model):
    _inherit = 'account.loan'

    asset_category_id = fields.Many2one(
        'account.asset.category', string='Right-of-use Asset Category', tracking=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        groups='account.group_account_invoice',
        help="Create the right-of-use asset of the lease in this category on its recognition, at the lease "
             "liability, depreciated over the lease term. The initial recognition debits the asset account of "
             "the category.")
    asset_id = fields.Many2one(
        'account.asset.asset', string='Right-of-use Asset', readonly=True, copy=False,
        groups='account.group_account_invoice')

    @api.constrains('asset_category_id', 'company_id')
    def _check_asset_category(self):
        for loan in self.sudo():
            category = loan.asset_category_id
            if category and (category.company_id != loan.company_id or category.type != 'purchase'):
                raise ValidationError(self.env._(
                    'The asset category %(category)s cannot hold the right of use of %(lease)s: choose an asset '
                    'category of its company.', category=category.display_name, lease=loan.display_name))

    @api.onchange('asset_category_id')
    def _onchange_asset_category_id(self):
        if self.asset_category_id:
            self.account_rou_id = self.asset_category_id.account_asset_id

    def write(self, vals):
        if 'asset_category_id' in vals and any(loan._has_entries() for loan in self):
            raise UserError(self.env._('The asset category of a recognized lease cannot change.'))
        return super().write(vals)

    def _rou_account(self):
        """ The asset account of the category of the right-of-use asset, when the lease has one. """
        self.ensure_one()
        return self.asset_category_id.account_asset_id or super()._rou_account()

    def _recognize_lease(self):
        """ Create the right-of-use asset with the recognition of the lease. """
        operation = super()._recognize_lease()
        if self.asset_category_id:
            self.asset_id = self._create_rou_asset()
        return operation

    def _prepare_rou_asset_values(self):
        """ The values of the right-of-use asset: the lease liability in the company currency, depreciated
        linearly from the start of the lease to the end of its term, in the periods of the category. """
        self.ensure_one()
        category = self.asset_category_id
        company = self.company_id
        currency = company.currency_id
        Asset = self.env['account.asset.asset']
        vals = {
            'name': self.env._('%(lease)s: right of use', lease=self.name),
            'code': self.name,
            'category_id': category.id,
            'value': currency.round(self.currency_id._convert(self.principal, currency, company, self.date_start)),
            'partner_id': self.partner_id.id,
            'company_id': company.id,
            'currency_id': currency.id,
            'date': self.date_start,
            **Asset.onchange_category_id_values(category.id)['value'],
        }
        vals.update({
            'method': 'linear',
            'method_time': 'end',
            'method_end': self._lease_term_end() - ONE_DAY,
            'prorata': True,
        })
        if vals.get('date_first_depreciation') == 'manual':
            # the periods of the asset follow the lease
            vals['first_depreciation_manual_date'] = add_months(self.date_start, vals['method_period']) - ONE_DAY
        return vals

    def _create_rou_asset(self):
        """ Create the right-of-use asset of the lease, confirmed when its category confirms its assets. """
        self.ensure_one()
        asset = self.env['account.asset.asset'].create(self._prepare_rou_asset_values())
        if self.asset_category_id.open_asset:
            asset.validate()
        self.message_post(body=Markup(self.env._('Right-of-use asset %s created.')) % asset._get_html_link())
        return asset

    def action_view_rou_asset(self):
        self.ensure_one()
        return self.asset_id._get_assets_action(self.env._('Right-of-use Asset'))
