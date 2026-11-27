from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rental_planning_warning = fields.Text(compute='_compute_rental_planning_warning', string="Unit Warnings")
    rental_by_units = fields.Boolean(compute='_compute_rental_planning_warning', string="Has Units")
    rental_slot_count = fields.Integer(compute='_compute_rental_slot_count', string="Unit Bookings")

    @api.depends('order_line.rental_unit_warning', 'order_line.rental_by_units')
    def _compute_rental_planning_warning(self):
        for order in self:
            lines = order.order_line.filtered('rental_by_units')
            order.rental_by_units = bool(lines)
            order.rental_planning_warning = '\n'.join(
                dict.fromkeys(filter(None, lines.mapped('rental_unit_warning')))) or False

    def _compute_rental_slot_count(self):
        for order in self:
            order.rental_slot_count = len(order.order_line.sudo().rental_slot_ids)

    def action_view_rental_slots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'om_sale_renting_planning.action_rental_unit_schedule')
        slots = self.order_line.sudo().rental_slot_ids
        action['domain'] = [('id', 'in', slots.ids)]
        action['context'] = {
            'om_planning_label': 'role',
            'create': False,
            'initialDate': fields.Datetime.to_string(min(slots.mapped('start_datetime'))) if slots else False,
        }
        action['name'] = self.env._("Bookings: %s", self.name)
        return action
