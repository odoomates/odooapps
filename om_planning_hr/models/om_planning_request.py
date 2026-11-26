from odoo import models


class OmPlanningRequest(models.Model):
    _inherit = 'om.planning.request'

    def _planning_approvers(self):
        """ The manager of the employee and the manager of their department approve too. """
        approvers = super()._planning_approvers()
        managers = self.resource_id._planning_get_manager_users()
        if self.request_type == 'switch':
            managers |= self.target_resource_id._planning_get_manager_users()
        return approvers | managers.filtered(lambda u: not u.share)
