from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_credit = fields.Monetary(related='partner_id.commercial_partner_id.credit', readonly=True)
    partner_credit_limit = fields.Monetary(related='partner_id.credit_limit_compute', readonly=True)
    show_partner_credit_warning = fields.Boolean(compute='_compute_show_partner_credit_warning')
    credit_limit_type = fields.Selection(related='company_id.credit_limit_type')

    @api.depends('partner_credit_limit', 'partner_credit', 'order_line',
                 'company_id.account_default_credit_limit', 'company_id.account_credit_limit')
    def _compute_show_partner_credit_warning(self):
        for order in self:
            account_credit_limit = order.company_id.account_credit_limit
            company_limit = order.partner_credit_limit == -1 and order.company_id.account_default_credit_limit
            partner_limit = order.partner_credit_limit + order.amount_total > 0 and order.partner_credit_limit
            partner_credit = order.partner_credit + order.amount_total
            order.show_partner_credit_warning = account_credit_limit and \
                                                ((company_limit and partner_credit > company_limit) or \
                                                (partner_limit and partner_credit > partner_limit))

    def action_confirm(self):
        result = super(SaleOrder, self).action_confirm()
        for so in self:
            if so.show_partner_credit_warning and so.credit_limit_type == 'block' and \
                    so.partner_credit + so.amount_total > so.partner_credit_limit:
                raise ValidationError(_("You cannot exceed credit limit !"))
        return result



