from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    is_technician = fields.Boolean(
        compute='_compute_is_technician', search='_search_is_technician', string="Technician",
        help="The employee has a field service planning role.")
    fs_job_count = fields.Integer(compute='_compute_fs_job_count', string="Field Service Jobs",
                                  groups='om_field_service.group_fs_user')

    @api.depends('resource_id.planning_role_ids.is_field_service')
    def _compute_is_technician(self):
        for employee in self:
            employee.is_technician = any(employee.resource_id.planning_role_ids.mapped('is_field_service'))

    def _search_is_technician(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        positive = (True in value) == (operator == 'in')
        domain = [('resource_id.planning_role_ids.is_field_service', '=', True)]
        return domain if positive else ['!', *domain]

    def _compute_fs_job_count(self):
        counts = dict(self.env['project.task']._read_group(
            [('technician_ids', 'in', self.ids), ('is_field_service', '=', True)],
            ['technician_ids'], ['__count']))
        for employee in self:
            employee.fs_job_count = counts.get(employee, 0)

    def action_view_fs_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('technician_ids', 'in', self.ids)]
        action['context'] = {'default_technician_ids': self.ids}
        return action
