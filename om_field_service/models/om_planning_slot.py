from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command

# slot fields that change the dates or the technicians of its job
JOB_SYNC_FIELDS = {'start_datetime', 'end_datetime', 'resource_ids', 'source_ref'}


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    fs_job_id = fields.Many2one(
        'project.task', compute='_compute_fs_job_id', store=True, index='btree_not_null',
        string="Field Service Job")
    fs_job_state = fields.Selection(related='fs_job_id.job_state', string="Job Status")
    fs_partner_id = fields.Many2one(related='fs_job_id.partner_id', string="Job Customer")
    fs_site_address = fields.Char(related='fs_job_id.site_address', string="Job Site")
    fs_job_type_id = fields.Many2one(related='fs_job_id.job_type_id', string="Type of Job")

    @api.depends('source_ref')
    def _compute_fs_job_id(self):
        for slot in self:
            record = slot.source_ref
            if record and record._name == 'project.task' and record.sudo().is_field_service:
                slot.fs_job_id = record.id
            else:
                slot.fs_job_id = False

    @api.model
    def _fs_technician_resources(self):
        return self.env['resource.resource'].search([
            ('planning_role_ids.is_field_service', '=', True),
            ('company_id', 'in', self.env.companies.ids + [False]),
        ])

    def _group_expand_resource_ids(self, resources, domain):
        if not self.env.context.get('om_fs_dispatch'):
            return super()._group_expand_resource_ids(resources, domain)
        if self._planning_expand_filtered(domain, ('resource_ids', 'department_id', 'id')):
            return resources
        return resources | self._fs_technician_resources()

    # ------------------------------------------------------------------
    # The job follows its slots
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        if not self.env.context.get('om_fs_no_sync'):
            slots.fs_job_id._fs_sync_from_slots()
        return slots

    def write(self, vals):
        jobs = self.fs_job_id
        res = super().write(vals)
        if JOB_SYNC_FIELDS & set(vals) and not self.env.context.get('om_fs_no_sync'):
            (jobs | self.fs_job_id)._fs_sync_from_slots()
        return res

    def unlink(self):
        jobs = self.fs_job_id
        res = super().unlink()
        if not self.env.context.get('om_fs_no_sync'):
            jobs.exists()._fs_sync_from_slots()
        return res

    # ------------------------------------------------------------------
    # Dispatch Gantt
    # ------------------------------------------------------------------

    @api.model
    def fs_plan_jobs(self, task_ids, defaults):
        """ Plan jobs in a cell of the dispatch Gantt: each job takes the first free period of the
        technician of the row in the cell (the start of the cell when they are busy).

        :param list task_ids: jobs to plan
        :param dict defaults: context defaults of the cell (dates, row values)
        :return: number of jobs planned
        """
        start = fields.Datetime.to_datetime(defaults.get('default_start_datetime'))
        stop = fields.Datetime.to_datetime(defaults.get('default_end_datetime'))
        if not (start and stop):
            return 0
        period = self.with_context(default_start_datetime=start)._adjust_cell_period(start, stop, {})
        start, stop = period.get('start_datetime', start), period.get('end_datetime', stop)
        resource_ids = self._ids_from_commands(defaults.get('default_resource_ids'))
        resources = self.env['resource.resource'].browse(resource_ids).exists()
        employees = resources.employee_id
        count = 0
        for job in self.env['project.task'].browse(task_ids).exists().filtered('is_field_service'):
            duration = timedelta(hours=job._fs_duration())
            begin = start
            if resources:
                free = resources[:1]._planning_free_intervals(start, max(stop, start + duration))
                for s, e, _recs in free[resources[:1].id]:
                    s = s.replace(tzinfo=None)
                    e = e.replace(tzinfo=None)
                    if e - max(s, start) >= duration:
                        begin = max(s, start)
                        break
            job.write({
                'planned_start': begin,
                'planned_end': begin + duration,
                'technician_ids': [Command.set(employees.ids)] if employees else [Command.clear()],
            })
            count += 1
        return count

    @api.model
    def fs_unplanned_jobs(self, limit=80):
        """ Jobs to plan, for the side panel of the dispatch Gantt. """
        jobs = self.env['project.task'].search([
            ('is_field_service', '=', True),
            ('planned_start', '=', False),
            ('job_state', 'not in', ('done', 'cancelled')),
        ], order='priority desc, date_deadline, id', limit=limit)
        return [{
            'id': job.id,
            'number': job.job_number or '',
            'name': job.name,
            'customer': job.partner_id.commercial_partner_id.name or '',
            'city': job.site_partner_id.city or '',
            'priority': job.priority,
            'deadline': fields.Datetime.to_string(job.date_deadline) if job.date_deadline else False,
            'duration': job._fs_duration(),
            'job_type': job.job_type_id.name or '',
        } for job in jobs]

    def action_open_fs_job(self):
        self.ensure_one()
        return self.fs_job_id and {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': self.fs_job_id.id,
            'view_mode': 'form',
            'views': [(self.env.ref('om_field_service.project_task_view_form_fs').id, 'form')],
        }
