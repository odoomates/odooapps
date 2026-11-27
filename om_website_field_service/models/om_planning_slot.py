from odoo import api, models
from odoo.fields import Domain


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    @api.model
    def _fs_unplanned_domain(self):
        # online requests still to review are not offered for planning
        return super()._fs_unplanned_domain() & Domain('fs_to_review', '=', False)
