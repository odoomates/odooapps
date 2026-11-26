from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_quality_lot_hold_reservation = fields.Boolean(
        string='Keep Lots on Hold out of Reservation', default=True,
        help="Lots and serial numbers on hold or rejected are skipped when Odoo picks the lots to reserve. "
             "A lot chosen by hand, or brought by the previous step of a route, is still reserved.")


