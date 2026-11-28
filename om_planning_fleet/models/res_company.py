from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    planning_fleet_follow_driver = fields.Boolean(
        string="Vehicles Follow Their Driver", default=True,
        help="New vehicles with a driver are added to the planning slots of the driver.")
