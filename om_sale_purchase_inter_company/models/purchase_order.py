from odoo import api, fields, models
from odoo.fields import Command
from odoo.tools import float_compare

TEXT_LINES = ('line_section', 'line_subsection', 'line_note')


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'om.inter.company.order.mixin']

    om_ic_sale_id = fields.Many2one(
        'sale.order', string="Inter-Company Sale", copy=False, readonly=True, index='btree_not_null',
        help="The sales order of the other company this order is linked with.")

    def _om_ic_counterpart(self):
        return self.om_ic_sale_id

    def _om_ic_rule(self):
        """(rule, company selling) for this purchase order, or (empty, False)."""
        self.ensure_one()
        order = self.sudo()
        Rule = self.env['om.inter.company.rule']
        target = order.partner_id.commercial_partner_id._om_ic_company()
        if not target or target == order.company_id:
            return Rule, False
        rule = Rule._om_ic_get(order.company_id, target)
        if not rule:
            return Rule, False
        return rule, target

    # ------------------------------------------------------------------
    # Confirmation: the sales order of the other company
    # ------------------------------------------------------------------

    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        if not self.env.context.get('om_ic_no_mirror'):
            for order in self.filtered(lambda o: o.state == 'purchase' and not o.om_ic_sale_id
                                       and not o.om_ic_is_mirror):
                rule, target = order._om_ic_rule()
                if rule and rule.mirror_purchase_orders:
                    order._om_ic_create_sale(rule, target)
        return res

    def _om_ic_create_sale(self, rule, target):
        self.ensure_one()
        order = self.sudo()
        skipped = []

        def create(env):
            vals = order._om_ic_prepare_sale_vals(rule, target, env, skipped)
            sale = env['sale.order'].create(vals)
            order.om_ic_sale_id = sale.id
            order.om_ic_rule_id = rule.id
            for line in sale.sudo().order_line.filtered('om_ic_purchase_line_id'):
                line.om_ic_purchase_line_id.om_ic_sale_line_id = line
            if rule.order_state == 'confirmed':
                sale.action_confirm()
            sale.sudo().message_post(body=self.env._(
                "Created from %(order)s of %(company)s.", order=order._get_html_link(), company=order.company_id.name))
            order.message_post(body=self.env._(
                "%(order)s created in %(company)s.", order=sale.sudo()._get_html_link(), company=target.name))

        done, error = self._om_ic_run(rule, target, create)
        if not done:
            order._om_ic_warn(self.env._("The sales order could not be created in %(company)s: %(error)s",
                                         company=target.name, error=error))
        elif skipped:
            order._om_ic_warn(self.env._(
                "Lines left out of the sales order of %(company)s, their products are not available there: "
                "%(products)s", company=target.name, products=', '.join(skipped)))

    def _om_ic_prepare_sale_vals(self, rule, target, env, skipped):
        self.ensure_one()
        warehouse = rule._om_ic_warehouse(target)
        salesperson = rule.salesperson_id or rule.user_id or env.user
        vals = {
            'partner_id': self.company_id.partner_id.id,
            'company_id': target.id,
            'client_order_ref': self.name,
            'origin': self.name,
            'user_id': salesperson.id,
            'om_ic_purchase_id': self.id,
            'om_ic_is_mirror': True,
            'om_ic_rule_id': rule.id,
            'order_line': [],
        }
        if warehouse:
            vals['warehouse_id'] = warehouse.id
        if self.date_planned:
            vals['commitment_date'] = self.date_planned
        currency = env['sale.order'].with_company(target).new({
            'partner_id': self.company_id.partner_id.id, 'company_id': target.id}).currency_id or target.currency_id
        for line in self.order_line:
            line_vals = line._om_ic_prepare_sale_line_vals(rule, target, currency, skipped)
            if line_vals:
                vals['order_line'].append(Command.create(line_vals))
        return vals

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def button_cancel(self):
        res = super().button_cancel()
        if not self.env.context.get('om_ic_no_mirror'):
            self._om_ic_cancelled()
        return res

    def _om_ic_cancelled(self):
        for order in self.sudo().filtered('om_ic_sale_id'):
            sale = order.om_ic_sale_id
            if sale.state == 'cancel':
                continue
            if order.om_ic_is_mirror:
                sale._om_ic_warn(self.env._(
                    "%(order)s of %(company)s, created from this order, was cancelled.",
                    order=order.name, company=order.company_id.name))
                continue
            rule = order.om_ic_rule_id or sale.om_ic_rule_id
            if not sale._om_ic_processed():
                done, _error = self._om_ic_run(
                    rule, sale.company_id, lambda env: env['sale.order'].browse(sale.id)._action_cancel())
                if done:
                    sale.message_post(body=self.env._(
                        "Cancelled as %(order)s of %(company)s was.", order=order._get_html_link(),
                        company=order.company_id.name))
                    continue
            sale._om_ic_warn(self.env._(
                "%(order)s of %(company)s, which this order was created from, was cancelled: this order is "
                "delivered or invoiced already, check it.", order=order.name, company=order.company_id.name))
            order._om_ic_warn(self.env._(
                "%(order)s of %(company)s is delivered or invoiced already and was not cancelled.",
                order=sale.name, company=sale.company_id.name))

    def _om_ic_processed(self):
        """Whether this order is received or billed, even in part."""
        self.ensure_one()
        lines = self.sudo().order_line.filtered(lambda l: not l.display_type)
        return any(line.qty_received or line.qty_invoiced for line in lines) or self.locked


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    om_ic_sale_line_id = fields.Many2one(
        'sale.order.line', string="Inter-Company Sale Line", copy=False, readonly=True, index='btree_not_null')

    def _om_ic_prepare_sale_line_vals(self, rule, target, currency, skipped):
        self.ensure_one()
        if self.display_type in TEXT_LINES:
            return {'display_type': self.display_type, 'name': self.name, 'sequence': self.sequence}
        if self.display_type or self.is_downpayment or not self.product_id:
            return None
        product = rule._om_ic_map_product(self.product_id, target)
        if not product:
            skipped.append(self.product_id.display_name)
            return None
        vals = {
            'sequence': self.sequence,
            'product_id': product.id,
            'name': self.name,
            'product_uom_qty': self.product_qty,
            'product_uom_id': self.uom_id.id,
            'om_ic_purchase_line_id': self.id,
        }
        if rule.keep_prices:
            price = self.price_unit
            if self.currency_id != currency:
                price = self.currency_id._convert(price, currency, target, fields.Date.context_today(self),
                                                  round=False)
            vals.update(price_unit=price, discount=self.discount)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get('om_ic_no_mirror'):
            lines.filtered(lambda l: l.order_id.om_ic_sale_id and l.state == 'purchase')._om_ic_added()
        return lines

    def write(self, vals):
        old = {}
        if 'product_qty' in vals and not self.env.context.get('om_ic_no_mirror'):
            old = {line.id: line.product_qty for line in self if line.om_ic_sale_line_id}
        res = super().write(vals)
        if old:
            self.filtered(lambda l: l.id in old)._om_ic_quantity_changed(old)
        return res

    def _om_ic_added(self):
        for line in self.sudo():
            order = line.order_id
            sale = order.om_ic_sale_id
            if order.om_ic_is_mirror or sale.state == 'cancel' or line.display_type or not line.product_id:
                if order.om_ic_is_mirror and not line.display_type:
                    sale._om_ic_warn(self.env._(
                        "A line with %(product)s was added to %(order)s of %(company)s, created from this order.",
                        product=line.product_id.display_name, order=order.name, company=order.company_id.name))
                continue
            rule = order.om_ic_rule_id or sale.om_ic_rule_id
            skipped = []
            vals = line._om_ic_prepare_sale_line_vals(rule, sale.company_id, sale.currency_id, skipped)
            if not vals:
                continue

            def add(env, vals=vals, sale=sale, line=line):
                new_line = env['sale.order.line'].create({**vals, 'order_id': sale.id})
                line.om_ic_sale_line_id = new_line.id

            done, error = order._om_ic_run(rule, sale.company_id, add)
            if done:
                sale.message_post(body=self.env._(
                    "Line with %(product)s added from %(order)s of %(company)s.",
                    product=line.product_id.display_name, order=order._get_html_link(), company=order.company_id.name))
            else:
                order._om_ic_warn(self.env._("The line with %(product)s was not added to %(order)s: %(error)s",
                                             product=line.product_id.display_name, order=sale.name, error=error))

    def _om_ic_quantity_changed(self, old):
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        for line in self.sudo():
            if not float_compare(old[line.id], line.product_qty, precision_digits=precision):
                continue
            order = line.order_id
            other = line.om_ic_sale_line_id
            sale = other.order_id
            if order.om_ic_is_mirror:
                sale._om_ic_warn(self.env._(
                    "The quantity of %(product)s was changed from %(old)s to %(new)s in %(order)s of %(company)s, "
                    "created from this order.", product=line.product_id.display_name, old=old[line.id],
                    new=line.product_qty, order=order.name, company=order.company_id.name))
                continue
            if sale.state == 'cancel':
                continue
            processed = other.qty_delivered or other.qty_invoiced or sale.locked
            if not processed:
                rule = order.om_ic_rule_id or sale.om_ic_rule_id
                qty = line.uom_id._compute_quantity(line.product_qty, other.product_uom_id)
                done, _error = order._om_ic_run(rule, sale.company_id, lambda env, other=other, qty=qty: (
                    env['sale.order.line'].browse(other.id).write({'product_uom_qty': qty})))
                if done:
                    sale.message_post(body=self.env._(
                        "Quantity of %(product)s changed to %(qty)s, as in %(order)s of %(company)s.",
                        product=other.product_id.display_name, qty=qty, order=order._get_html_link(),
                        company=order.company_id.name))
                    continue
            sale._om_ic_warn(self.env._(
                "The quantity of %(product)s was changed from %(old)s to %(new)s in %(order)s of %(company)s, "
                "which this order was created from: this line is delivered or invoiced already, check it.",
                product=line.product_id.display_name, old=old[line.id], new=line.product_qty,
                order=order.name, company=order.company_id.name))
            order._om_ic_warn(self.env._(
                "%(order)s of %(company)s is delivered or invoiced already: its quantity of %(product)s was not "
                "changed.", order=sale.name, company=sale.company_id.name,
                product=line.product_id.display_name))
