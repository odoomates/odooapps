from odoo import fields, models


class OmPlanningRole(models.Model):
    _inherit = 'om.planning.role'

    is_field_service = fields.Boolean(
        string="Field Service", help="The resources of this role are field service technicians: they are "
                                     "the rows of the dispatch Gantt and the technicians suggested for the jobs.")
