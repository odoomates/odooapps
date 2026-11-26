import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

TEXT_LINES = ('line_section', 'line_subsection', 'line_note')


class OmInterCompanyOrderMixin(models.AbstractModel):
    """What the sales and purchase orders share between two companies of the group: the warning shown
    when the order of the other company could not follow, and the button to open it."""
    _name = 'om.inter.company.order.mixin'
    _description = 'Inter-Company Order'

    om_ic_warning = fields.Text(string="Inter-Company Warning", copy=False, readonly=True)
    om_ic_is_mirror = fields.Boolean(
        string="Created by Inter-Company", copy=False, readonly=True,
        help="The order was created from the order of the other company.")
    om_ic_rule_id = fields.Many2one('om.inter.company.rule', string="Inter-Company Rule", copy=False, readonly=True)
    om_ic_link_name = fields.Char(compute='_compute_om_ic_link', string="Inter-Company Order")
    om_ic_link_company = fields.Char(compute='_compute_om_ic_link', string="Inter-Company Order Company")

    def _om_ic_counterpart(self):
        """The order of the other company linked with this one."""
        raise NotImplementedError

    def _compute_om_ic_link(self):
        for order in self:
            other = order.sudo()._om_ic_counterpart()
            order.om_ic_link_name = other.name if other else False
            order.om_ic_link_company = other.company_id.name if other else False

    def _om_ic_warn(self, text):
        for order in self.sudo():
            order.om_ic_warning = text
            order.message_post(body=Markup('<p class="text-warning">%s</p>') % text)

    def action_om_ic_dismiss(self):
        self.sudo().om_ic_warning = False
        return True

    def action_om_ic_open(self):
        self.ensure_one()
        other = self.sudo()._om_ic_counterpart()
        if not other:
            return False
        if other.company_id not in self.env.user.company_ids:
            raise UserError(self.env._("%(order)s is in %(company)s, a company you have no access to.",
                                       order=other.name, company=other.company_id.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': other._name,
            'res_id': other.id,
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': self.env._("Inter-Company"),
        }

    def _om_ic_run(self, rule, company, function):
        """Run ``function(env)`` in ``company`` as the user of ``rule``; False when it failed (the error is
        returned as the second value)."""
        try:
            with self.env.cr.savepoint():
                function(rule._om_ic_env(company))
            return True, False
        except (UserError, ValidationError, AccessError) as error:
            _logger.info("Inter-company order not followed: %s", error)
            return False, error.args[0] if error.args else str(error)


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'om.inter.company.order.mixin']

    om_ic_purchase_id = fields.Many2one(
        'purchase.order', string="Inter-Company Purchase", copy=False, readonly=True, index='btree_not_null',
        help="The purchase order of the other company this order is linked with.")

    def _om_ic_counterpart(self):
        return self.om_ic_purchase_id

    def _om_ic_rule(self):
        """(rule, company buying) for this sales order, or (empty, False)."""
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
    # Confirmation: the purchase order of the other company
    # ------------------------------------------------------------------

    def _action_confirm(self):
        res = super()._action_confirm()
        if not self.env.context.get('om_ic_no_mirror'):
            for order in self.filtered(lambda o: not o.om_ic_purchase_id and not o.om_ic_is_mirror):
                rule, target = order._om_ic_rule()
                if rule and rule.mirror_sale_orders:
                    order._om_ic_create_purchase(rule, target)
        return res

    def _om_ic_create_purchase(self, rule, target):
        self.ensure_one()
        order = self.sudo()
        skipped = []

        def create(env):
            vals = order._om_ic_prepare_purchase_vals(rule, target, env, skipped)
            purchase = env['purchase.order'].create(vals)
            order.om_ic_purchase_id = purchase.id
            order.om_ic_rule_id = rule.id
            for line in purchase.sudo().order_line.filtered('om_ic_sale_line_id'):
                line.om_ic_sale_line_id.om_ic_purchase_line_id = line
            if rule.order_state == 'confirmed':
                purchase.button_confirm()
            purchase.sudo().message_post(body=self.env._(
                "Created from %(order)s of %(company)s.", order=order._get_html_link(), company=order.company_id.name))
            order.message_post(body=self.env._(
                "%(order)s created in %(company)s.", order=purchase.sudo()._get_html_link(), company=target.name))

        done, error = self._om_ic_run(rule, target, create)
        if not done:
            order._om_ic_warn(self.env._("The purchase order could not be created in %(company)s: %(error)s",
                                         company=target.name, error=error))
        elif skipped:
            order._om_ic_warn(self.env._(
                "Lines left out of the purchase order of %(company)s, their products are not available there: "
                "%(products)s", company=target.name, products=', '.join(skipped)))

    def _om_ic_prepare_purchase_vals(self, rule, target, env, skipped):
        self.ensure_one()
        picking_type = rule._om_ic_receipt_type(target)
        buyer = rule.buyer_id or rule.user_id or env.user
        vals = {
            'partner_id': self.company_id.partner_id.id,
            'company_id': target.id,
            'partner_ref': self.name,
            'origin': self.name,
            'user_id': buyer.id,
            'om_ic_sale_id': self.id,
            'om_ic_is_mirror': True,
            'om_ic_rule_id': rule.id,
            'order_line': [],
        }
        if picking_type:
            vals['picking_type_id'] = picking_type.id
        if rule.keep_prices:
            vals['currency_id'] = self.currency_id.id
        date_planned = self.commitment_date or self.expected_date
        for line in self.order_line:
            line_vals = line._om_ic_prepare_purchase_line_vals(rule, target, date_planned, skipped)
            if line_vals:
                vals['order_line'].append(Command.create(line_vals))
        return vals

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def _action_cancel(self):
        res = super()._action_cancel()
        if not self.env.context.get('om_ic_no_mirror'):
            self._om_ic_cancelled()
        return res

    def _om_ic_cancelled(self):
        for order in self.sudo().filtered('om_ic_purchase_id'):
            purchase = order.om_ic_purchase_id
            if purchase.state == 'cancel':
                continue
            if order.om_ic_is_mirror:
                purchase._om_ic_warn(self.env._(
                    "%(order)s of %(company)s, created from this order, was cancelled.",
                    order=order.name, company=order.company_id.name))
                continue
            rule = order.om_ic_rule_id or purchase.om_ic_rule_id
            if not purchase._om_ic_processed():
                done, _error = self._om_ic_run(
                    rule, purchase.company_id, lambda env: env['purchase.order'].browse(purchase.id).button_cancel())
                if done:
                    purchase.message_post(body=self.env._(
                        "Cancelled as %(order)s of %(company)s was.", order=order._get_html_link(),
                        company=order.company_id.name))
                    continue
            purchase._om_ic_warn(self.env._(
                "%(order)s of %(company)s, which this order was created from, was cancelled: this order is "
                "received or billed already, check it.", order=order.name, company=order.company_id.name))
            order._om_ic_warn(self.env._(
                "%(order)s of %(company)s is received or billed already and was not cancelled.",
                order=purchase.name, company=purchase.company_id.name))

    def _om_ic_processed(self):
        """Whether this order is delivered or invoiced, even in part."""
        self.ensure_one()
        lines = self.sudo().order_line.filtered(lambda l: not l.display_type)
        return any(line.qty_delivered or line.qty_invoiced for line in lines) or self.locked


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    om_ic_purchase_line_id = fields.Many2one(
        'purchase.order.line', string="Inter-Company Purchase Line", copy=False, readonly=True,
        index='btree_not_null')

    def _om_ic_prepare_purchase_line_vals(self, rule, target, date_planned, skipped):
        self.ensure_one()
        if self.display_type in TEXT_LINES:
            return {'display_type': self.display_type, 'name': self.name, 'sequence': self.sequence,
                    'product_qty': 0}
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
            'product_qty': self.product_uom_qty,
            'uom_id': self.product_uom_id.id,
            'om_ic_sale_line_id': self.id,
        }
        if date_planned:
            vals['date_planned'] = date_planned
        if rule.keep_prices:
            vals.update(price_unit=self.price_unit, discount=self.discount)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get('om_ic_no_mirror'):
            lines.filtered(lambda l: l.order_id.om_ic_purchase_id and l.state == 'sale')._om_ic_added()
        return lines

    def write(self, vals):
        old = {}
        if 'product_uom_qty' in vals and not self.env.context.get('om_ic_no_mirror'):
            old = {line.id: line.product_uom_qty for line in self if line.om_ic_purchase_line_id}
        res = super().write(vals)
        if old:
            self.filtered(lambda l: l.id in old)._om_ic_quantity_changed(old)
        return res

    def _om_ic_added(self):
        for line in self.sudo():
            order = line.order_id
            purchase = order.om_ic_purchase_id
            if order.om_ic_is_mirror or purchase.state == 'cancel' or line.display_type or not line.product_id:
                if order.om_ic_is_mirror and not line.display_type:
                    purchase._om_ic_warn(self.env._(
                        "A line with %(product)s was added to %(order)s of %(company)s, created from this order.",
                        product=line.product_id.display_name, order=order.name, company=order.company_id.name))
                continue
            rule = order.om_ic_rule_id or purchase.om_ic_rule_id
            skipped = []
            vals = line._om_ic_prepare_purchase_line_vals(rule, purchase.company_id, purchase.date_planned, skipped)
            if not vals:
                continue

            def add(env, vals=vals, purchase=purchase, line=line):
                new_line = env['purchase.order.line'].create({**vals, 'order_id': purchase.id})
                line.om_ic_purchase_line_id = new_line.id

            done, error = order._om_ic_run(rule, purchase.company_id, add)
            if done:
                purchase.message_post(body=self.env._(
                    "Line with %(product)s added from %(order)s of %(company)s.",
                    product=line.product_id.display_name, order=order._get_html_link(), company=order.company_id.name))
            else:
                order._om_ic_warn(self.env._("The line with %(product)s was not added to %(order)s: %(error)s",
                                             product=line.product_id.display_name, order=purchase.name, error=error))

    def _om_ic_quantity_changed(self, old):
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        for line in self.sudo():
            if not float_compare(old[line.id], line.product_uom_qty, precision_digits=precision):
                continue
            order = line.order_id
            other = line.om_ic_purchase_line_id
            purchase = other.order_id
            if order.om_ic_is_mirror:
                purchase._om_ic_warn(self.env._(
                    "The quantity of %(product)s was changed from %(old)s to %(new)s in %(order)s of %(company)s, "
                    "created from this order.", product=line.product_id.display_name, old=old[line.id],
                    new=line.product_uom_qty, order=order.name, company=order.company_id.name))
                continue
            if purchase.state == 'cancel':
                continue
            processed = other.qty_received or other.qty_invoiced or purchase.locked
            if not processed:
                rule = order.om_ic_rule_id or purchase.om_ic_rule_id
                qty = line.product_uom_id._compute_quantity(line.product_uom_qty, other.uom_id)
                done, _error = order._om_ic_run(rule, purchase.company_id, lambda env, other=other, qty=qty: (
                    env['purchase.order.line'].browse(other.id).write({'product_qty': qty})))
                if done:
                    purchase.message_post(body=self.env._(
                        "Quantity of %(product)s changed to %(qty)s, as in %(order)s of %(company)s.",
                        product=other.product_id.display_name, qty=qty, order=order._get_html_link(),
                        company=order.company_id.name))
                    continue
            purchase._om_ic_warn(self.env._(
                "The quantity of %(product)s was changed from %(old)s to %(new)s in %(order)s of %(company)s, "
                "which this order was created from: this line is received or billed already, check it.",
                product=line.product_id.display_name, old=old[line.id], new=line.product_uom_qty,
                order=order.name, company=order.company_id.name))
            order._om_ic_warn(self.env._(
                "%(order)s of %(company)s is received or billed already: its quantity of %(product)s was not "
                "changed.", order=purchase.name, company=purchase.company_id.name,
                product=line.product_id.display_name))
