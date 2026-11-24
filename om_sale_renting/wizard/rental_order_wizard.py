from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import format_amount


class OmRentalOrderWizard(models.TransientModel):
    _name = 'om.rental.order.wizard'
    _description = "Rental Pickup and Return"

    order_id = fields.Many2one('sale.order', string="Rental Order", required=True, ondelete='cascade')
    mode = fields.Selection(
        [('pickup', "Pickup"), ('return', "Return")], string="Operation", required=True, default='pickup')
    line_ids = fields.One2many(
        'om.rental.order.wizard.line', 'wizard_id', string="Products", compute='_compute_line_ids',
        store=True, readonly=False)
    note = fields.Text(string="Notes")
    currency_id = fields.Many2one(related='order_id.currency_id')
    late_fee_amount = fields.Monetary(
        string="Late Fees", compute='_compute_late_fee_amount', currency_field='currency_id')
    add_late_fee = fields.Boolean(string="Add Late Fees", default=True)
    damage_description = fields.Char(string="Damages / Extra Charges")
    damage_amount = fields.Monetary(string="Extra Charge Amount", currency_field='currency_id')

    @api.depends('order_id', 'mode')
    def _compute_line_ids(self):
        for wizard in self:
            commands = [Command.clear()]
            for line in wizard.order_id.order_line.filtered('is_rental'):
                if wizard.mode == 'pickup':
                    qty_max = line.product_uom_qty - line.qty_picked_up
                else:
                    qty_max = line.qty_picked_up - line.qty_returned
                if line.product_uom_id.compare(qty_max, 0) <= 0:
                    continue
                commands.append(Command.create({
                    'sale_line_id': line.id,
                    'qty_max': qty_max,
                    'qty': qty_max,
                }))
            wizard.line_ids = commands

    @api.depends('line_ids.late_fee', 'mode')
    def _compute_late_fee_amount(self):
        for wizard in self:
            wizard.late_fee_amount = sum(wizard.line_ids.mapped('late_fee')) if wizard.mode == 'return' else 0.0

    def _om_rental_process_stock(self):
        """Hook to move the stock of the processed lines."""
        return True

    def action_validate(self):
        self.ensure_one()
        order = self.order_id
        lines = self.line_ids.filtered(lambda line: line.uom_id.compare(line.qty, 0) > 0)
        if not lines:
            raise UserError(self.env._("Set the quantity of at least one product."))
        for line in lines:
            if line.uom_id.compare(line.qty, line.qty_max) > 0:
                raise UserError(self.env._(
                    "You cannot process more than %(qty)s %(uom)s of %(product)s.",
                    qty=line.qty_max, uom=line.uom_id.name, product=line.product_id.display_name))
        self._om_rental_process_stock()
        summary = []
        for line in lines:
            sol = line.sale_line_id
            if self.mode == 'pickup':
                vals = {'qty_picked_up': sol.qty_picked_up + line.qty}
                if sol.qty_delivered_method == 'manual':
                    vals['qty_delivered'] = sol.qty_delivered + line.qty
                sol.write(vals)
            else:
                sol.qty_returned = sol.qty_returned + line.qty
            summary.append("%s %s %s" % (line.qty, line.uom_id.name, line.product_id.display_name))
            if line.note:
                summary[-1] += " (%s)" % line.note

        lines.sale_line_id._rental_sync_booking()
        if self.mode == 'return':
            self._om_rental_add_charges(lines)

        title = self.env._("Picked up") if self.mode == 'pickup' else self.env._("Returned")
        body = self.env._("%(title)s: %(products)s", title=title, products=", ".join(summary))
        if self.note:
            body += "\n" + self.note
        order.message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}

    def _om_rental_add_charges(self, lines):
        order = self.order_id
        company = order.company_id
        new_lines = []
        if self.add_late_fee:
            late_product = company.rental_late_product_id or self.env.ref(
                'om_sale_renting.product_rental_late_fee', raise_if_not_found=False)
            for line in lines.filtered(lambda line: line.late_fee > 0):
                if not late_product:
                    raise UserError(self.env._("Set a late fee product in the rental settings."))
                new_lines.append({
                    'order_id': order.id,
                    'product_id': late_product.id,
                    'name': self.env._(
                        "Late return of %(product)s: %(delay)s",
                        product=line.product_id.display_name, delay=line.late_label),
                    'product_uom_qty': 1,
                    'price_unit': line.late_fee,
                })
        if self.damage_amount:
            damage_product = company.rental_damage_product_id or self.env.ref(
                'om_sale_renting.product_rental_damage', raise_if_not_found=False)
            if not damage_product:
                raise UserError(self.env._("Set a damage product in the rental settings."))
            new_lines.append({
                'order_id': order.id,
                'product_id': damage_product.id,
                'name': self.damage_description or damage_product.display_name,
                'product_uom_qty': 1,
                'price_unit': self.damage_amount,
            })
        if new_lines:
            created = self.env['sale.order.line'].create(new_lines)
            order.message_post(body=self.env._(
                "Charges added: %(charges)s",
                charges=", ".join(
                    "%s %s" % (line.name, format_amount(self.env, line.price_subtotal, order.currency_id))
                    for line in created)))


class OmRentalOrderWizardLine(models.TransientModel):
    _name = 'om.rental.order.wizard.line'
    _description = "Rental Pickup and Return Line"

    wizard_id = fields.Many2one('om.rental.order.wizard', required=True, ondelete='cascade')
    sale_line_id = fields.Many2one('sale.order.line', string="Order Line", required=True, ondelete='cascade')
    product_id = fields.Many2one(related='sale_line_id.product_id')
    uom_id = fields.Many2one(related='sale_line_id.product_uom_id')
    qty_reserved = fields.Float(related='sale_line_id.product_uom_qty', string="Reserved")
    qty_max = fields.Float(string="Open Quantity", digits='Product Unit')
    qty = fields.Float(string="Quantity", digits='Product Unit')
    note = fields.Char(string="Note")
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    late_hours = fields.Float(string="Late Hours", compute='_compute_late')
    late_label = fields.Char(string="Delay", compute='_compute_late')
    late_fee = fields.Monetary(string="Late Fee", compute='_compute_late', currency_field='currency_id')

    @api.depends('sale_line_id', 'qty', 'wizard_id.mode')
    def _compute_late(self):
        now = fields.Datetime.now()
        for line in self:
            sol = line.sale_line_id
            hours = sol._om_rental_late_hours(now) if line.wizard_id.mode == 'return' and sol else 0.0
            line.late_hours = hours
            line.late_label = sol._om_rental_format_span(sol.rental_return_date, now) if hours else False
            fee = sol.product_id.product_tmpl_id._om_rental_late_fee(hours) * line.qty if hours else 0.0
            product_currency = sol.product_id.currency_id
            currency = sol.order_id.currency_id
            if fee and product_currency and currency and product_currency != currency:
                fee = product_currency._convert(fee, currency, sol.company_id, fields.Date.context_today(line))
            line.late_fee = fee
