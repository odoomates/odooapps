from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssetSell(models.TransientModel):
    _name = 'asset.sell'
    _description = 'Sell or Dispose Asset'

    asset_id = fields.Many2one(
        'account.asset.asset', string='Asset', required=True, ondelete='cascade')
    asset_state = fields.Selection(related='asset_id.state', string='Asset Status')
    company_id = fields.Many2one(related='asset_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    action = fields.Selection(
        [('sell', 'Sell'), ('dispose', 'Dispose')],
        string='Action', required=True, default='sell',
    )
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    note = fields.Text(string='Reason')
    sale_invoice_ids = fields.Many2many(
        'account.move', string='Customer Invoices',
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),"
               " ('company_id', '=', company_id)]",
        help="Invoices recording the sale of this asset. Their product lines give the "
             "sale price the gain or the loss is computed from.",
    )
    sale_amount = fields.Monetary(string='Sale Price', compute='_compute_sale_amount')
    book_value = fields.Monetary(related='asset_id.book_value', string='Book Value Today')
    account_asset_gain_id = fields.Many2one(
        related='asset_id.category_id.account_asset_gain_id', readonly=False)
    account_asset_loss_id = fields.Many2one(
        related='asset_id.category_id.account_asset_loss_id', readonly=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if not res.get('asset_id') and self.env.context.get('active_model') == 'account.asset.asset':
            res['asset_id'] = self.env.context.get('active_id')
        return res

    def _sale_lines(self):
        self.ensure_one()
        return self.sale_invoice_ids.line_ids.filtered(
            lambda line: line.display_type == 'product')

    @api.depends('sale_invoice_ids')
    def _compute_sale_amount(self):
        for wizard in self:
            wizard.sale_amount = -sum(wizard._sale_lines().mapped('balance'))

    def action_confirm(self):
        self.ensure_one()
        sale_lines = self.env['account.move.line']
        if self.action == 'sell':
            sale_lines = self._sale_lines()
            if not sale_lines:
                raise UserError(_('Select the customer invoices recording the sale.'))
        return self.asset_id.dispose(disposal_date=self.date, sale_lines=sale_lines,
                                     note=self.note)
