from odoo import fields, models


class OmFsTimer(models.Model):
    """ A running timer of a technician on a job: stopping it writes a timesheet. """
    _name = 'om.fs.timer'
    _description = "Field Service Timer"
    _order = 'start desc'

    task_id = fields.Many2one('project.task', string="Job", required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string="User", required=True, default=lambda self: self.env.user,
                              index=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    time_type = fields.Selection([
        ('travel', 'Travel'),
        ('work', 'Work'),
    ], string="Time Type", required=True, default='work')
    start = fields.Datetime(string="Started On", required=True, default=fields.Datetime.now)
    company_id = fields.Many2one(related='task_id.company_id', store=True, string="Company")

    def _fs_stop(self, description=None):
        """ Stop the timers: one timesheet per timer, with the time spent (one minute at least).

        :return: the timesheets created
        """
        Line = self.env['account.analytic.line']
        now = fields.Datetime.now()
        values_list = []
        for timer in self:
            hours = max((now - timer.start).total_seconds() / 3600, 1 / 60)
            task = timer.task_id
            if timer.time_type == 'travel':
                name = self.env._("Travel to %s", task.site_partner_id.display_name or task.name)
            else:
                name = description or self.env._("Work: %s", task.name)
            values_list.append({
                'name': name,
                'task_id': task.id,
                'project_id': task.project_id.id,
                'employee_id': timer.employee_id.id,
                'user_id': timer.user_id.id,
                'date': fields.Date.context_today(timer, timer.start),
                'unit_amount': round(hours, 4),
                'fs_time_type': timer.time_type,
            })
        lines = Line.sudo().create(values_list) if values_list else Line
        self.sudo().unlink()
        return lines
