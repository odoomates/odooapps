from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

RENTAL_STATUS = [
    ('draft', "Quotation"),
    ('sent', "Quotation Sent"),
    ('reserved', "Reserved"),
    ('pickup', "Picked Up"),
    ('returned', "Returned"),
    ('cancel', "Cancelled"),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_rental_order = fields.Boolean(string="Rental Order", index=True)
    rental_start_date = fields.Datetime(
        string="Pickup Date", compute='_compute_rental_period', store=True, readonly=False,
        precompute=True, copy=True)
    rental_return_date = fields.Datetime(
        string="Return Date", compute='_compute_rental_period', store=True, readonly=False,
        precompute=True, copy=True)
    rental_status = fields.Selection(
        RENTAL_STATUS, string="Rental Status", compute='_compute_rental_status', store=True,
        index=True)
    is_late = fields.Boolean(
        string="Late", compute='_compute_is_late', search='_search_is_late',
        help="The return date has passed and some products are not returned yet.")
    rental_duration_display = fields.Char(string="Duration", compute='_compute_rental_duration_display')
    rental_has_pickable = fields.Boolean(compute='_compute_rental_actions')
    rental_has_returnable = fields.Boolean(compute='_compute_rental_actions')
    rental_pickup_reminder_sent = fields.Boolean(copy=False)
    rental_return_reminder_sent = fields.Boolean(copy=False)

    _rental_period_check = models.Constraint(
        'CHECK(rental_start_date IS NULL OR rental_return_date IS NULL '
        'OR rental_return_date > rental_start_date)',
        "The return date must be after the pickup date.",
    )

    @api.depends('is_rental_order')
    def _compute_rental_period(self):
        for order in self:
            if not order.is_rental_order:
                continue
            if not order.rental_start_date:
                now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
                order.rental_start_date = now + timedelta(hours=1)
            if not order.rental_return_date or order.rental_return_date <= order.rental_start_date:
                order.rental_return_date = order.rental_start_date + timedelta(days=1)

    @api.depends('state', 'is_rental_order', 'order_line.is_rental', 'order_line.product_uom_qty',
                 'order_line.qty_picked_up', 'order_line.qty_returned')
    def _compute_rental_status(self):
        for order in self:
            if not order.is_rental_order:
                order.rental_status = False
                continue
            if order.state in ('draft', 'sent', 'cancel'):
                order.rental_status = order.state
                continue
            lines = order.order_line.filtered('is_rental')
            if lines and all(line.qty_returned >= line.product_uom_qty for line in lines):
                order.rental_status = 'returned'
            elif any(line.qty_picked_up > line.qty_returned for line in lines):
                order.rental_status = 'pickup'
            else:
                order.rental_status = 'reserved'

    @api.depends('rental_status', 'rental_return_date', 'order_line.rental_return_date')
    def _compute_is_late(self):
        now = fields.Datetime.now()
        for order in self:
            order.is_late = bool(
                order.rental_status in ('reserved', 'pickup')
                and any(line.rental_return_date and line.rental_return_date < now
                        and line.qty_returned < line.product_uom_qty
                        for line in order.order_line.filtered('is_rental'))
            )

    def _search_is_late(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        now = fields.Datetime.now()
        lines = self.env['sale.order.line'].sudo().search([
            ('is_rental', '=', True),
            ('order_id.rental_status', 'in', ('reserved', 'pickup')),
            ('rental_return_date', '<', now),
        ])
        order_ids = lines.filtered(lambda line: line.qty_returned < line.product_uom_qty).order_id.ids
        positive = (operator == 'in') == (True in value)
        return Domain('id', 'in' if positive else 'not in', order_ids)

    @api.depends('rental_start_date', 'rental_return_date')
    def _compute_rental_duration_display(self):
        for order in self:
            order.rental_duration_display = self.env['sale.order.line']._om_rental_format_span(
                order.rental_start_date, order.rental_return_date)

    @api.depends('state', 'order_line.is_rental', 'order_line.product_uom_qty',
                 'order_line.qty_picked_up', 'order_line.qty_returned')
    def _compute_rental_actions(self):
        for order in self:
            lines = order.order_line.filtered('is_rental') if order.state == 'sale' else self.env['sale.order.line']
            order.rental_has_pickable = any(line.qty_picked_up < line.product_uom_qty for line in lines)
            order.rental_has_returnable = any(line.qty_returned < line.qty_picked_up for line in lines)

    @api.onchange('rental_start_date', 'rental_return_date')
    def _onchange_rental_dates(self):
        lines = self.order_line.filtered('is_rental')
        for line in lines:
            line.rental_start_date = self.rental_start_date
            line.rental_return_date = self.rental_return_date
        lines._om_rental_update_lines()

    def write(self, vals):
        res = super().write(vals)
        if 'rental_start_date' in vals or 'rental_return_date' in vals:
            lines = self.order_line.filtered('is_rental')
            if 'order_line' not in vals:
                lines._om_rental_update_lines()
            lines.filtered(lambda line: line.state == 'sale')._rental_sync_booking()
        return res

    def _action_confirm(self):
        res = super()._action_confirm()
        self.order_line.filtered('is_rental')._rental_sync_booking()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        self.order_line.filtered('is_rental')._rental_sync_booking()
        return res

    def _get_confirmation_template(self):
        self.ensure_one()
        if self.is_rental_order:
            template = self.env.ref('om_sale_renting.mail_template_rental_confirmation', raise_if_not_found=False)
            if template:
                return template
        return super()._get_confirmation_template()

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def _om_rental_open_wizard(self, mode):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(self.env._("Confirm the rental order first."))
        title = self.env._("Pickup") if mode == 'pickup' else self.env._("Return")
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'om.rental.order.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_mode': mode},
        }

    def action_rental_pickup(self):
        return self._om_rental_open_wizard('pickup')

    def action_rental_return(self):
        return self._om_rental_open_wizard('return')

    def action_rental_print_agreement(self):
        return self.env.ref('om_sale_renting.action_report_rental_agreement').report_action(self)

    @api.model
    def _cron_rental_reminders(self):
        """Send the pickup and return reminders of the coming rentals."""
        now = fields.Datetime.now()
        for company in self.env['res.company'].search([]):
            limit = now + timedelta(hours=company.rental_reminder_hours or 24)
            pickup_template = self.env.ref('om_sale_renting.mail_template_rental_pickup_reminder',
                                           raise_if_not_found=False)
            return_template = self.env.ref('om_sale_renting.mail_template_rental_return_reminder',
                                           raise_if_not_found=False)
            to_pick = self.search([
                ('company_id', '=', company.id),
                ('rental_status', '=', 'reserved'),
                ('rental_pickup_reminder_sent', '=', False),
                ('rental_start_date', '>=', now),
                ('rental_start_date', '<=', limit),
            ])
            for order in to_pick:
                order._send_order_notification_mail(pickup_template, allow_deferred_sending=False)
            to_pick.rental_pickup_reminder_sent = True
            to_return = self.search([
                ('company_id', '=', company.id),
                ('rental_status', '=', 'pickup'),
                ('rental_return_reminder_sent', '=', False),
                ('rental_return_date', '>=', now),
                ('rental_return_date', '<=', limit),
            ])
            for order in to_return:
                order._send_order_notification_mail(return_template, allow_deferred_sending=False)
            to_return.rental_return_reminder_sent = True

    def _rental_process_demo(self, mode):
        """Pick up or return all the rental lines (demo data)."""
        for order in self:
            wizard = self.env['om.rental.order.wizard'].with_context(
                default_order_id=order.id, default_mode=mode).create({'add_late_fee': False})
            wizard.action_validate()
