from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    rental_availability = fields.Selection([
        ('quantity', "By Quantity"),
        ('unit', "By Units"),
    ], string="Availability", default='quantity', required=True,
        help="By quantity: a number of identical items is free or not. By units: each rental books "
             "one of the units of the product in the planning, so maintenance, field service and the "
             "other rentals of that unit are taken into account.")
    rental_unit_ids = fields.Many2many(
        'resource.resource', 'om_rental_product_unit_rel', 'product_tmpl_id', 'resource_id',
        string="Rental Units", domain="[('resource_type', '=', 'material')]",
        help="Units rented as this product: equipment, vehicles, rooms or other planning resources.")
    rental_unit_count = fields.Integer(compute='_compute_rental_unit_count', string="Number of Units")
    rental_padding_before_hours = fields.Float(
        string="Preparation Before",
        help="Hours the unit is booked before the pickup (loading, transport, setup).")
    rental_staff_role_id = fields.Many2one(
        'om.planning.role', string="Staff Role",
        help="People planned with each rental of the product: a delivery or setup slot before the "
             "pickup and a collection slot after the return.")
    rental_staff_count = fields.Integer(string="Staff per Rental", default=1)
    rental_staff_hours = fields.Float(string="Staff Time", default=1.0,
                                      help="Hours of the delivery slot and of the collection slot.")

    @api.depends('rental_unit_ids')
    def _compute_rental_unit_count(self):
        for template in self:
            template.rental_unit_count = len(template.rental_unit_ids)

    def action_view_rental_unit_schedule(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'om_sale_renting_planning.action_rental_unit_schedule')
        action['domain'] = [('material_resource_ids', 'in', self.rental_unit_ids.ids)]
        action['context'] = dict(
            self.env.context, om_planning_label='role',
            om_planning_material_rows=[('id', 'in', self.rental_unit_ids.ids)])
        action['name'] = self.env._("Unit Schedule: %s", self.display_name)
        return action

    @api.model
    def _rental_planning_demo_units(self):
        """ Demo data: the demo equipment are the units of the demo rental products. """
        pairs = (
            ('om_sale_renting_planning.product_rental_lift_product_template',
             ('om_planning_maintenance.equipment_scissor_lift', 'om_planning_maintenance.equipment_scissor_lift_2')),
            ('om_sale_renting_planning.product_rental_generator_product_template',
             ('om_planning_maintenance.equipment_generator',)),
        )
        for template_xmlid, equipment_xmlids in pairs:
            template = self.env.ref(template_xmlid, raise_if_not_found=False)
            equipment = self.env['maintenance.equipment']
            for xmlid in equipment_xmlids:
                equipment |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['maintenance.equipment']
            equipment._planning_ensure_resource()
            if template and equipment:
                template.rental_unit_ids = [fields.Command.set(equipment.resource_id.ids)]
