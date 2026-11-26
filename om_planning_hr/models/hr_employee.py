from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    planning_role_ids = fields.Many2many(
        related='resource_id.planning_role_ids', readonly=False, string="Planning Roles")
    planning_default_role_id = fields.Many2one(
        related='resource_id.planning_default_role_id', readonly=False, string="Default Planning Role")
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_count', string="Planning Slots",
                                         groups='om_planning.group_planning_manager')

    def _compute_planning_slot_count(self):
        counts = dict(self.env['om.planning.slot']._read_group(
            [('resource_ids', 'in', self.resource_id.ids)], ['resource_ids'], ['__count']))
        for employee in self:
            employee.planning_slot_count = counts.get(employee.resource_id, 0)

    def action_view_planning(self):
        self.ensure_one()
        action = self.resource_id.action_view_planning()
        action['name'] = self.env._("Planning: %s", self.name)
        return action
