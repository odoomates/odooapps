from odoo import api, fields, models


class AssetPause(models.TransientModel):
    _name = 'asset.pause'
    _description = 'Pause or Resume Asset'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True, ondelete='cascade')
    asset_state = fields.Selection(related='asset_id.state')
    pause_date = fields.Date(related='asset_id.pause_date')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    note = fields.Text(string='Reason')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if not res.get('asset_id') and self.env.context.get('active_model') == 'account.asset.asset':
            res['asset_id'] = self.env.context.get('active_id')
        return res

    def action_apply(self):
        """ Pause a running asset, resume a paused one. """
        self.ensure_one()
        if self.asset_state == 'paused':
            self.asset_id.resume(self.date, note=self.note)
        else:
            self.asset_id.pause(self.date, note=self.note)
        return {'type': 'ir.actions.act_window_close'}
