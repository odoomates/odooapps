from odoo import fields, models


class OmQualityPoint(models.Model):
    _inherit = 'om.quality.point'

    point_type = fields.Selection(
        selection_add=[('production', 'Manufacturing Orders'), ('workorder', 'Work Order Steps')],
        ondelete={'production': 'set default', 'workorder': 'set default'})
    operation_ids = fields.Many2many(
        'mrp.routing.workcenter', 'om_quality_point_operation_rel', 'point_id', 'operation_id',
        string='Operations', check_company=True,
        help="The work orders of these operations get the check. Leave empty with no work centre for every work order.")
    workcenter_ids = fields.Many2many(
        'mrp.workcenter', 'om_quality_point_workcenter_rel', 'point_id', 'workcenter_id',
        string='Work Centres', check_company=True,
        help="The work orders done in these work centres get the check.")

    def _filter_workorder(self, workorder):
        """ The work order step points of `self` that apply to `workorder`. """
        def match(point):
            if not point.operation_ids and not point.workcenter_ids:
                return True
            return workorder.operation_id in point.operation_ids or workorder.workcenter_id in point.workcenter_ids
        return self.filtered(match)
