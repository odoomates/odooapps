from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.account_asset import _month_fraction

DURATION_FIELD_BY_TIME_METHOD = {
    'number': 'method_number',
    'end': 'method_end',
    'rate': 'method_rate',
}


class AssetModify(models.TransientModel):
    _name = 'asset.modify'
    _description = 'Modify Asset'

    note = fields.Text(string='Reason', required=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='asset_id.currency_id')
    company_id = fields.Many2one(related='asset_id.company_id')
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        help="The running period is depreciated up to this date before the changes apply."
    )
    method_number = fields.Integer(string='Number of Depreciation', required=True)
    method_period = fields.Integer(string='Period Length')
    method_end = fields.Date(string='Ending date')
    method_rate = fields.Float(string='Depreciation Rate (%)')
    asset_method_time = fields.Selection(related='asset_id.method_time', string='Asset Method Time')
    value_at_date = fields.Monetary(
        string='Current Depreciable Value', compute='_compute_value_at_date',
        help="Value left to depreciate once the running period is depreciated up to the date."
    )
    new_depreciable_value = fields.Monetary(
        string='New Depreciable Value',
        compute='_compute_new_values', store=True, readonly=False,
        help="Lower than the current value: a re-evaluation entry records the loss of value. "
             "Higher: an asset is created for the value increase."
    )
    new_salvage_value = fields.Monetary(
        string='New Salvage Value',
        compute='_compute_new_values', store=True, readonly=False,
    )
    increase_counterpart_account_id = fields.Many2one(
        'account.account', string='Value Increase Counterpart',
        check_company=True,
        help="Account credited by the entry increasing the gross value of the asset."
    )
    is_value_increase = fields.Boolean(compute='_compute_is_value_increase')

    @api.depends('asset_id', 'date')
    def _compute_value_at_date(self):
        for wizard in self:
            asset = wizard.asset_id
            if asset.state == 'open' and wizard.date:
                wizard.value_at_date = (
                    asset._get_residual_at(wizard.date) - asset._get_partial_depreciation(wizard.date)[1])
            else:
                wizard.value_at_date = asset.value_residual

    @api.depends('value_at_date', 'new_depreciable_value', 'new_salvage_value')
    def _compute_is_value_increase(self):
        for wizard in self:
            new_book_value = wizard.new_depreciable_value + wizard.new_salvage_value
            wizard.is_value_increase = wizard.currency_id.compare_amounts(
                new_book_value, wizard.value_at_date + wizard.asset_id.salvage_value) > 0

    @api.depends('value_at_date')
    def _compute_new_values(self):
        """ Nothing changes by default: the values of the asset at the date. """
        for wizard in self:
            wizard.new_depreciable_value = wizard.value_at_date
            wizard.new_salvage_value = wizard.asset_id.salvage_value

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        asset = self.env['account.asset.asset'].browse(res.get('asset_id') or self.env.context.get('active_id'))
        if asset:
            res['asset_id'] = asset.id
            res.update({
                field_name: asset[field_name]
                for field_name in ('method_number', 'method_period', 'method_end', 'method_rate')
                if field_name in fields
            })
        return res

    def _check_modification(self):
        asset = self.asset_id
        currency = asset.currency_id
        if asset.state != 'open':
            raise UserError(_('Only running assets can be modified.'))
        if self.date < asset.date - timedelta(days=1):
            raise UserError(_('"%s" cannot be modified before its acquisition.', asset.name))
        if currency.compare_amounts(self.new_depreciable_value, 0.0) < 0 \
                or currency.compare_amounts(self.new_salvage_value, 0.0) < 0:
            raise UserError(_('The new depreciable and salvage values must be positive.'))
        asset._check_lock_date(self.date)

    def modify(self):
        """ Apply the new duration and values from `date`: the running period is first depreciated
        up to that day, a lower value is recorded by a re-evaluation entry, a higher value by a
        value increase asset, then the rest of the board is computed again. """
        self.ensure_one()
        self._check_modification()
        asset = self.asset_id
        currency = asset.currency_id
        changed_fields = ['method_period', DURATION_FIELD_BY_TIME_METHOD[asset.method_time], 'salvage_value']
        previous_values = {field_name: asset[field_name] for field_name in changed_fields}

        asset._depreciate_until(self.date)
        previous_book_value = asset._get_residual_at(self.date) + asset.salvage_value
        asset.write({
            'method_period': self.method_period,
            DURATION_FIELD_BY_TIME_METHOD[asset.method_time]: self[DURATION_FIELD_BY_TIME_METHOD[asset.method_time]],
            'salvage_value': self.new_salvage_value,
        })
        life_left = asset._get_lifetime_months() - _month_fraction(asset._get_lifetime_start(), self.date)
        if life_left <= 0 and not currency.is_zero(self.new_depreciable_value):
            raise UserError(_('The new duration of "%s" ends before the date of the modification.', asset.name))

        depreciable_value = asset._get_residual_at(self.date)
        if currency.compare_amounts(depreciable_value, 0.0) < 0:
            raise UserError(_('The new salvage value of "%s" is higher than its value in the books.', asset.name))
        difference = currency.round(self.new_depreciable_value - depreciable_value)
        if currency.compare_amounts(difference, 0.0) < 0:
            self.env['account.move'].create(
                asset._prepare_depreciation_move_vals(-difference, self.date, self.date, entry_type='revaluation'),
            )._post(soft=True)
        elif currency.compare_amounts(difference, 0.0) > 0:
            if not self.increase_counterpart_account_id:
                raise UserError(_('Choose the counterpart account of the value increase of "%s".', asset.name))
            asset._create_value_increase(self.date, difference, self.increase_counterpart_account_id)
        asset._recompute_board(keep_until=self.date)

        dummy, tracking_values = asset._mail_track(
            self.env['account.asset.asset'].fields_get(changed_fields), previous_values)
        body = self.note
        if not currency.is_zero(difference):
            body = _('%(note)s. Book value changed from %(before)s to %(after)s.',
                     note=self.note, before=previous_book_value, after=previous_book_value + difference)
        asset.message_post(subject=_('Asset modified'), body=body, message_type='tracking',
                           tracking_values=tracking_values)
        return {'type': 'ir.actions.act_window_close'}
