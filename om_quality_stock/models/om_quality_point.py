from odoo import api, fields, models
from odoo.exceptions import ValidationError


class OmQualityPoint(models.Model):
    _inherit = 'om.quality.point'

    point_type = fields.Selection(
        selection_add=[('picking', 'Transfers')], ondelete={'picking': 'set default'})
    picking_type_ids = fields.Many2many(
        'stock.picking.type', 'om_quality_point_picking_type_rel', 'point_id', 'picking_type_id',
        string='Operation Types', check_company=True,
        help="The receipts, deliveries or internal transfers that get the check.")

    @api.constrains('point_type', 'picking_type_ids')
    def _check_picking_types(self):
        for point in self:
            if point.point_type == 'picking' and not point.picking_type_ids:
                raise ValidationError(self.env._("Choose the operation types of the control point %s.", point.name))
