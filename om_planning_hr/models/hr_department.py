from odoo import models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    def action_view_planning(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_slot')
        action['name'] = self.env._("Planning: %s", self.name)
        action['domain'] = [('department_id', 'child_of', self.id)]
        return action
