from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    om_referrer_id = fields.Many2one(
        'res.partner', string='Referrer', compute='_compute_om_referrer_id', store=True, readonly=False,
        precompute=True, index='btree_not_null', tracking=True, check_company=True,
        help='Reseller or partner who brought the sale: earns the reseller commission. '
             'It is copied to the invoices.')

    @api.depends('partner_id')
    def _compute_om_referrer_id(self):
        for order in self:
            if order.state in ('draft', 'sent') or not order.om_referrer_id:
                referrer = order.partner_id.om_referrer_id or order.partner_id.commercial_partner_id.om_referrer_id
                if referrer or not order.om_referrer_id:
                    order.om_referrer_id = referrer

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        if self.om_referrer_id:
            values['om_referrer_id'] = self.om_referrer_id.id
        return values
