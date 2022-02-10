from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_credit = fields.Monetary(related='partner_id.commercial_partner_id.credit', readonly=True)
    partner_credit_limit = fields.Monetary(related='partner_id.credit_limit_compute', readonly=True)
    show_partner_credit_warning = fields.Boolean(compute='_compute_show_partner_credit_warning')

    @api.depends('partner_credit_limit', 'partner_credit',
                 'company_id.account_default_credit_limit', 'company_id.account_credit_limit')
    def _compute_show_partner_credit_warning(self):
        for order in self:
            account_credit_limit = order.company_id.account_credit_limit
            company_limit = order.partner_credit_limit == -1 and order.company_id.account_default_credit_limit
            partner_limit = order.partner_credit_limit > 0 and order.partner_credit_limit
            order.show_partner_credit_warning = account_credit_limit and \
                                                ((company_limit and order.partner_credit > company_limit) or \
                                                (partner_limit and order.partner_credit > partner_limit))


