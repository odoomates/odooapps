from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rental_late_product_id = fields.Many2one(
        'product.product', string="Late Fee Product",
        help="Service product used for the late return fees added to rental orders.")
    rental_damage_product_id = fields.Many2one(
        'product.product', string="Damage Product",
        help="Service product used for the damages and extra charges added at return.")
    rental_terms = fields.Html(string="Rental Terms", translate=True)
    rental_reminder_hours = fields.Integer(
        string="Reminder Delay", default=24,
        help="Pickup and return reminders are sent this many hours before the date.")

    @api.model
    def _om_rental_set_default_products(self):
        late = self.env.ref('om_sale_renting.product_rental_late_fee', raise_if_not_found=False)
        damage = self.env.ref('om_sale_renting.product_rental_damage', raise_if_not_found=False)
        for company in self.search([]):
            if late and not company.rental_late_product_id:
                company.rental_late_product_id = late
            if damage and not company.rental_damage_product_id:
                company.rental_damage_product_id = damage
