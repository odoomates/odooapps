from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    om_quality_quarantine = fields.Boolean(
        string='Quarantine Location', copy=False,
        help="Goods put aside by a failed quality check. A route does not take goods out of it by itself.")
