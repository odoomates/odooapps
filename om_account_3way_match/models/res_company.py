from odoo import fields, models

OM_3WAY_FIELDS = {
    'om_3way_enabled', 'om_3way_price_tol_percent', 'om_3way_price_tol_amount', 'om_3way_qty_tol_percent',
    'om_3way_ordered_policy', 'om_3way_no_po_policy',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_3way_enabled = fields.Boolean(string='3-Way Matching', default=True)
    om_3way_price_tol_percent = fields.Float(string='Price Tolerance (%)', digits=(16, 2))
    om_3way_price_tol_amount = fields.Monetary(string='Price Tolerance per Unit', currency_field='currency_id')
    om_3way_qty_tol_percent = fields.Float(string='Quantity Tolerance (%)', digits=(16, 2))
    om_3way_ordered_policy = fields.Selection(
        [('two_way', 'Match the purchase order only (2-way)'),
         ('three_way', 'Also wait for the receipt (3-way)')],
        string='Products Billed on Ordered Quantities', default='two_way', required=True)
    om_3way_no_po_policy = fields.Selection(
        [('release', 'Release to pay'), ('manual', 'Wait for a manual release')],
        string='Bills without Purchase Order', default='release', required=True)
    om_3way_payment_policy = fields.Selection(
        [('none', 'Allow'), ('warn', 'Warn'), ('block', 'Block')],
        string='Payment of Bills not Released', default='warn', required=True)
    om_3way_activity = fields.Boolean(string='Activity on Exceptions')

    def write(self, vals):
        res = super().write(vals)
        if OM_3WAY_FIELDS.intersection(vals):
            self._om_recompute_release()
        return res

    def _om_recompute_release(self):
        """ Recompute the match of the open vendor bills after a change of the settings. """
        bills = self.env['account.move'].sudo().search([
            ('company_id', 'in', self.ids),
            ('move_type', '=', 'in_invoice'),
            ('state', '!=', 'cancel'),
            ('payment_state', 'not in', ('paid', 'reversed')),
        ])
        if bills:
            self.env.add_to_compute(self.env['account.move.line']._fields['om_match_state'], bills.invoice_line_ids)
            self.env.add_to_compute(self.env['account.move']._fields['om_release_state'], bills)
