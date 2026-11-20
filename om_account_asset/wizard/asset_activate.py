from odoo import api, fields, models


class AssetActivate(models.TransientModel):
    _name = 'asset.activate'
    _description = 'Activate the Depreciation of an Asset'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='asset_id.company_id')
    date = fields.Date(string='Start Depreciating On', required=True, default=fields.Date.context_today)
    category_id = fields.Many2one(
        'account.asset.category', string='Category', required=True,
        domain="[('type', '=', 'purchase'), ('method', '!=', 'none'), ('company_id', '=', company_id)]",
        help='The asset takes the depreciation method of this category; when the category books its assets on '
             'another account, the value is moved there.')
    note = fields.Text(string='Reason')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if not res.get('asset_id') and self.env.context.get('active_model') == 'account.asset.asset':
            res['asset_id'] = self.env.context.get('active_id')
        return res

    def action_apply(self):
        self.ensure_one()
        self.asset_id.activate_depreciation(self.date, self.category_id, note=self.note)
        return {'type': 'ir.actions.act_window_close'}
