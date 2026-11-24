from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_late_product_id = fields.Many2one(
        related='company_id.rental_late_product_id', readonly=False)
    rental_damage_product_id = fields.Many2one(
        related='company_id.rental_damage_product_id', readonly=False)
    rental_terms = fields.Html(related='company_id.rental_terms', readonly=False)
    rental_reminder_hours = fields.Integer(related='company_id.rental_reminder_hours', readonly=False)
