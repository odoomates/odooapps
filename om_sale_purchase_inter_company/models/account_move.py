from odoo import models
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _om_ic_prepare_mirror_vals(self, rule, target, env):
        vals = super()._om_ic_prepare_mirror_vals(rule, target, env)
        source = self.sudo()
        if vals['move_type'] in ('in_invoice', 'in_refund'):
            orders = source.invoice_line_ids.sale_line_ids.order_id.om_ic_purchase_id.filtered(
                lambda o: o.company_id == target)
        else:
            orders = source.invoice_line_ids.purchase_line_id.order_id.om_ic_sale_id.filtered(
                lambda o: o.company_id == target)
        if orders:
            vals['invoice_origin'] = ', '.join(orders.mapped('name'))
        return vals

    def _om_ic_prepare_mirror_line_vals(self, line, rule, target, journal, is_sale, fiscal_position, currency,
                                        rate_date):
        vals = super()._om_ic_prepare_mirror_line_vals(
            line, rule, target, journal, is_sale, fiscal_position, currency, rate_date)
        if not vals or vals.get('display_type') != 'product':
            return vals
        line = line.sudo()
        if is_sale:
            # a vendor bill of a purchase order made from a sales order of this company, or the reverse
            sale_lines = line.purchase_line_id.om_ic_sale_line_id.filtered(lambda l: l.company_id == target)
            if sale_lines:
                vals['sale_line_ids'] = [Command.set(sale_lines.ids)]
        else:
            purchase_line = line.sale_line_ids.om_ic_purchase_line_id.filtered(lambda l: l.company_id == target)[:1]
            if purchase_line:
                vals['purchase_line_id'] = purchase_line.id
        return vals
