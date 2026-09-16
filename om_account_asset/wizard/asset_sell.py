from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AssetSell(models.TransientModel):
    _name = 'asset.sell'
    _description = 'Sell or Dispose Asset'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='asset_id.company_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    action = fields.Selection(
        [('sell', 'Sell'), ('dispose', 'Dispose')],
        string='Action', required=True, default='sell',
    )
    scope = fields.Selection(
        [('full', 'Whole Asset'), ('partial', 'Part of the Asset')],
        string='Disposed Of', required=True, default='full',
    )
    disposed_percent = fields.Float(
        string='Share Disposed Of (%)', digits=(16, 2), default=50.0,
        help="Share of the asset in the books today: its gross value, salvage value and depreciation "
             "decrease in the same proportion.",
    )
    disposed_value = fields.Monetary(
        string='Gross Value Disposed Of', compute='_compute_disposed_value', currency_field='asset_currency_id')
    asset_currency_id = fields.Many2one(related='asset_id.currency_id', string='Asset Currency')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    note = fields.Text(string='Reason')
    sale_invoice_ids = fields.Many2many(
        'account.move', string='Customer Invoices',
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('company_id', '=', company_id)]",
    )
    sale_line_ids = fields.Many2many(
        'account.move.line', string='Sale Lines',
        compute='_compute_sale_line_ids', store=True, readonly=False,
        domain="[('move_id', 'in', sale_invoice_ids), ('display_type', '=', 'product')]",
        help="Lines of the customer invoices recording the sale of this asset.",
    )
    asset_gain_account_id = fields.Many2one(related='company_id.asset_gain_account_id', readonly=False)
    asset_loss_account_id = fields.Many2one(related='company_id.asset_loss_account_id', readonly=False)
    book_value = fields.Monetary(related='asset_id.book_value', string='Book Value Today')
    sale_amount = fields.Monetary(string='Sale Price', compute='_compute_sale_amount')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if not res.get('asset_id') and self.env.context.get('active_model') == 'account.asset.asset':
            res['asset_id'] = self.env.context.get('active_id')
        return res

    @api.depends('asset_id.value', 'disposed_percent', 'scope')
    def _compute_disposed_value(self):
        for wizard in self:
            share = wizard.disposed_percent / 100.0 if wizard.scope == 'partial' else 1.0
            wizard.disposed_value = wizard.asset_currency_id.round(wizard.asset_id.value * share)

    @api.depends('sale_invoice_ids')
    def _compute_sale_line_ids(self):
        for wizard in self:
            product_lines = self.env['account.move.line']
            for invoice in wizard.sale_invoice_ids:
                product_lines |= invoice.line_ids.filtered(lambda line: line.display_type == 'product')
            wizard.sale_line_ids = product_lines

    @api.depends('sale_line_ids')
    def _compute_sale_amount(self):
        for wizard in self:
            wizard.sale_amount = -sum(wizard.sale_line_ids.mapped('balance'))

    def action_confirm(self):
        self.ensure_one()
        sale_lines = self.env['account.move.line']
        if self.action == 'sell':
            if not self.sale_line_ids:
                raise UserError(_('Select the invoice lines of the sale.'))
            sale_lines = self.sale_line_ids
        if self.scope == 'partial':
            move = self.asset_id._dispose_partially(self.date, self.disposed_percent / 100.0,
                                                    sale_lines=sale_lines, note=self.note)
            return self.asset_id._open_record_action(move)
        return self.asset_id.set_to_close(sale_lines=sale_lines, disposal_date=self.date, note=self.note)
