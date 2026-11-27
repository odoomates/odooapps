import base64
import math
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.om_field_service.wizard.om_fs_plan_wizard import _distance_km
from odoo.addons.om_field_service.wizard.om_fs_route_wizard import maps_route_url

JOB_STATES = [
    ('new', 'New'),
    ('planned', 'Planned'),
    ('travelling', 'Travelling'),
    ('in_progress', 'In Progress'),
    ('waiting_parts', 'Waiting for Parts'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]
# jobs a technician works on: shown on the phone screen whatever their date
ACTIVE_STATES = ('travelling', 'in_progress', 'waiting_parts')
CLOSED_STATES = ('done', 'cancelled')
# job fields copied to the planning slot
SLOT_SYNC_FIELDS = {'planned_start', 'planned_end', 'technician_ids', 'job_state', 'name', 'job_number'}


class ProjectTask(models.Model):
    _name = 'project.task'
    _inherit = ['project.task', 'om.planning.source']

    is_field_service = fields.Boolean(related='project_id.is_field_service', store=True, index=True,
                                      string="Field Service Job")
    job_number = fields.Char(string="Job Number", copy=False, readonly=True, index='btree_not_null')
    job_type_id = fields.Many2one('om.fs.job.type', string="Job Type", tracking=True, index='btree_not_null',
                                  domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    job_state = fields.Selection(JOB_STATES, string="Job Status", default='new', required=True, copy=False,
                                 tracking=True, index=True, group_expand=True)
    site_partner_id = fields.Many2one(
        'res.partner', string="Site", compute='_compute_site_partner_id', store=True, readonly=False,
        index='btree_not_null', tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Address where the work is done: the delivery address of the customer by default.")
    site_address = fields.Char(compute='_compute_site_address', string="Site Address")
    site_latitude = fields.Float(related='site_partner_id.partner_latitude', string="Site Latitude")
    site_longitude = fields.Float(related='site_partner_id.partner_longitude', string="Site Longitude")
    site_map_url = fields.Char(compute='_compute_site_address', string="Directions")
    site_equipment = fields.Text(string="Equipment at Site",
                                 help="Equipment worked on: model, serial number, location in the building.")
    planned_start = fields.Datetime(string="Planned Start", copy=False, tracking=True, index=True)
    planned_end = fields.Datetime(string="Planned End", copy=False, tracking=True)
    technician_ids = fields.Many2many(
        'hr.employee', 'om_fs_task_technician_rel', 'task_id', 'employee_id', string="Technicians",
        domain="[('company_id', 'in', [company_id, False])]", tracking=True,
        help="Employees who do the job: their users are added to the assignees.")
    checklist_line_ids = fields.One2many('om.fs.checklist.line', 'task_id', string="Checklist Items", copy=True)
    checklist_progress = fields.Integer(compute='_compute_checklist_progress', string="Checklist Progress")
    work_summary = fields.Html(string="Work Done", copy=False,
                               help="What was done on site, shown on the job report.")
    photo_ids = fields.Many2many('ir.attachment', 'om_fs_task_photo_rel', 'task_id', 'attachment_id',
                                 string="Photos", copy=False)
    photo_count = fields.Integer(compute='_compute_photo_count', string="Photo Count")
    customer_signature = fields.Binary(string="Customer Signature", copy=False, attachment=True)
    signed_by = fields.Char(string="Signed By", copy=False)
    signed_on = fields.Datetime(string="Signed On", copy=False)
    date_done = fields.Datetime(string="Done On", copy=False, readonly=True)
    travel_hours = fields.Float(compute='_compute_fs_hours', string="Travel Time")
    work_hours = fields.Float(compute='_compute_fs_hours', string="Work Time")
    fs_timer_ids = fields.One2many('om.fs.timer', 'task_id', string="Running Timers")
    fs_my_timer = fields.Selection([
        ('travel', 'Travelling'),
        ('work', 'Working'),
    ], compute='_compute_fs_my_timer', string="My Timer")
    fs_my_timer_start = fields.Datetime(compute='_compute_fs_my_timer', string="My Timer Start")
    fs_signature_required = fields.Boolean(related='job_type_id.signature_required', string="Signature Needed")
    # live tracking page of the customer: the last position of the technician, only while on the way
    fs_track_token = fields.Char(string="Tracking Token", copy=False, readonly=True, index='btree_not_null',
                                 groups='om_field_service.group_fs_user')
    fs_track_latitude = fields.Float(string="Technician Latitude", digits=(10, 7), copy=False, readonly=True,
                                     groups='om_field_service.group_fs_user')
    fs_track_longitude = fields.Float(string="Technician Longitude", digits=(10, 7), copy=False, readonly=True,
                                      groups='om_field_service.group_fs_user')
    fs_track_date = fields.Datetime(string="Position Updated On", copy=False, readonly=True,
                                    groups='om_field_service.group_fs_user')
    fs_tracking_url = fields.Char(compute='_compute_fs_tracking_url', string="Tracking Link",
                                  help="Page where the customer follows the technician on the way.")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('partner_id')
    def _compute_site_partner_id(self):
        for task in self:
            if not task.partner_id:
                continue
            if task.site_partner_id and task.site_partner_id.commercial_partner_id == \
                    task.partner_id.commercial_partner_id:
                continue
            task.site_partner_id = task.partner_id.address_get(['delivery'])['delivery']

    @api.depends('site_partner_id.street', 'site_partner_id.city', 'site_partner_id.zip',
                 'site_partner_id.partner_latitude', 'site_partner_id.partner_longitude')
    def _compute_site_address(self):
        for task in self:
            partner = task.site_partner_id
            task.site_address = partner._fs_address_line() if partner else False
            task.site_map_url = partner._fs_map_urls().get('google') if partner else False

    @api.depends('fs_track_token', 'company_id.fs_live_tracking')
    def _compute_fs_tracking_url(self):
        for task in self:
            token = task.sudo().fs_track_token
            enabled = task._fs_company().fs_live_tracking if task.is_field_service else False
            task.fs_tracking_url = f'{task.get_base_url()}/field-service/track/{token}' if token and enabled else False

    @api.depends('checklist_line_ids.is_done')
    def _compute_checklist_progress(self):
        for task in self:
            lines = task.checklist_line_ids
            task.checklist_progress = round(100 * len(lines.filtered('is_done')) / len(lines)) if lines else 0

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for task in self:
            task.photo_count = len(task.photo_ids)

    @api.depends('timesheet_ids.unit_amount', 'timesheet_ids.fs_time_type')
    def _compute_fs_hours(self):
        for task in self:
            lines = task.sudo().timesheet_ids
            task.travel_hours = sum(lines.filtered(lambda l: l.fs_time_type == 'travel').mapped('unit_amount'))
            task.work_hours = sum(lines.filtered(lambda l: l.fs_time_type != 'travel').mapped('unit_amount'))

    @api.depends('fs_timer_ids')
    @api.depends_context('uid')
    def _compute_fs_my_timer(self):
        for task in self:
            timer = task.fs_timer_ids.filtered(lambda t: t.user_id == self.env.user)[:1]
            task.fs_my_timer = timer.time_type or False
            task.fs_my_timer_start = timer.start

    # ------------------------------------------------------------------
    # Onchanges
    # ------------------------------------------------------------------

    @api.onchange('job_type_id')
    def _onchange_job_type_id(self):
        job_type = self.job_type_id
        if not job_type:
            return
        if job_type.default_duration:
            self.allocated_hours = job_type.default_duration
            if self.planned_start:
                self.planned_end = self.planned_start + timedelta(hours=job_type.default_duration)
        if not self.checklist_line_ids.filtered('is_done'):
            self.checklist_line_ids = [Command.clear()] + [
                Command.create(values) for values in job_type.checklist_line_ids._fs_line_values()]

    @api.onchange('planned_start')
    def _onchange_planned_start(self):
        if self.planned_start and (not self.planned_end or self.planned_end <= self.planned_start):
            self.planned_end = self.planned_start + timedelta(hours=self._fs_duration())

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get('om_fs_job') and 'project_id' in fields and not res.get('project_id'):
            project = self.env['project.project'].search(
                [('is_field_service', '=', True), ('company_id', 'in', [self.env.company.id, False])], limit=1)
            if project:
                res['project_id'] = project.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        jobs = tasks.filtered('is_field_service')
        for job in jobs:
            values = {}
            if not job.job_number:
                values['job_number'] = self.env['ir.sequence'].next_by_code('om.fs.job') or False
            if job.job_type_id:
                if not job.allocated_hours and job.job_type_id.default_duration:
                    values['allocated_hours'] = job.job_type_id.default_duration
                if not job.checklist_line_ids:
                    values['checklist_line_ids'] = [
                        Command.create(line) for line in job.job_type_id.checklist_line_ids._fs_line_values()]
            if values:
                job.with_context(om_fs_no_sync=True).write(values)
        jobs._fs_sync_assignees()
        if not self.env.context.get('om_fs_no_sync'):
            jobs.filtered(lambda j: j.planned_start and j.planned_end)._fs_sync_slots()
        return tasks

    def write(self, vals):
        if 'technician_ids' in vals:
            old_users = {task.id: task.sudo().technician_ids.user_id for task in self}
        planning = self.filtered(lambda t: t.job_state != 'planned') if vals.get('job_state') == 'planned' else None
        res = super().write(vals)
        if vals.get('job_state') and vals['job_state'] != 'travelling':
            # the position of the technician is only kept while they are on the way
            self.sudo().filtered('fs_track_date').write(
                {'fs_track_latitude': 0.0, 'fs_track_longitude': 0.0, 'fs_track_date': False})
        jobs = self.filtered('is_field_service')
        if not jobs:
            return res
        if planning:
            (planning & jobs)._fs_on_planned()
        if vals.get('project_id'):
            jobs.filtered(lambda j: not j.job_number).with_context(om_fs_no_sync=True).write({
                'job_number': self.env['ir.sequence'].next_by_code('om.fs.job')})
        if 'technician_ids' in vals:
            jobs._fs_sync_assignees(old_users)
        if 'job_type_id' in vals:
            for job in jobs.filtered(lambda j: j.job_type_id and not j.checklist_line_ids):
                job.checklist_line_ids = [
                    Command.create(line) for line in job.job_type_id.checklist_line_ids._fs_line_values()]
        if SLOT_SYNC_FIELDS & set(vals) and not self.env.context.get('om_fs_no_sync'):
            jobs._fs_sync_slots()
        return res

    def _fs_on_planned(self):
        """ Hook called when jobs get planned (from New to Planned): tell the customer through the
        channels of :meth:`_fs_notify_channels`. """
        if self.env.context.get('install_mode') or self.env.context.get('om_fs_no_notify'):
            return
        for job in self.filtered('partner_id'):
            job._fs_notify_channels('planned')

    def _fs_sync_assignees(self, old_users=None):
        """ The users of the technicians are assignees of the job. """
        for task in self:
            users = task.sudo().technician_ids.user_id.with_env(self.env)
            removed = (old_users or {}).get(task.id, self.env['res.users']) - users
            commands = [Command.link(user.id) for user in users - task.user_ids]
            commands += [Command.unlink(user.id) for user in removed & task.user_ids]
            if commands:
                task.with_context(om_fs_no_sync=True).write({'user_ids': commands})

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _fs_duration(self):
        self.ensure_one()
        return self.allocated_hours or self.job_type_id.default_duration or 1.0

    def _planning_hours_to_plan(self):
        self.ensure_one()
        if not self.is_field_service:
            return super()._planning_hours_to_plan()
        return self.allocated_hours

    def _planning_role(self):
        self.ensure_one()
        if not self.is_field_service:
            return super()._planning_role()
        return self.job_type_id.role_id or self.env.ref(
            'om_field_service.planning_role_technician', raise_if_not_found=False) or super()._planning_role()

    def _planning_slot_values(self):
        values = super()._planning_slot_values()
        if self.is_field_service:
            values.update({
                'name': self._fs_slot_name(),
                'note': self.site_address or False,
            })
            if self.technician_ids:
                values['resource_ids'] = [Command.set(self.sudo().technician_ids.resource_id.ids)]
        return values

    def _fs_slot_name(self):
        self.ensure_one()
        name = ' '.join(filter(None, [self.job_number, self.name]))
        customer = self.partner_id.commercial_partner_id.name
        return f'{name} - {customer}' if customer else name

    def _fs_slots(self):
        return self.env['om.planning.slot'].sudo().search(
            [('source_ref', 'in', self._planning_source_refs())])

    def _fs_sync_slots(self):
        """ The planning slot of the job follows its planned dates and technicians. """
        Slot = self.env['om.planning.slot'].sudo().with_context(
            om_fs_no_sync=True, om_planning_keep_published=True, recurrence_update='this')
        for job in self.filtered('is_field_service'):
            slots = job._fs_slots().with_context(Slot.env.context)
            if job.job_state == 'cancelled' or not job.planned_start:
                slots.unlink()
                continue
            if not job.planned_end or job.planned_end <= job.planned_start:
                continue
            if len(slots) > 1:
                # several slots (work over several days): the dates come from the slots
                slots.write({'name': job._fs_slot_name()})
                continue
            values = {
                'name': job._fs_slot_name(),
                'start_datetime': job.planned_start,
                'end_datetime': job.planned_end,
                'resource_ids': [Command.set(job.sudo().technician_ids.resource_id.ids)],
            }
            if slots:
                slots.write(values)
            else:
                Slot.create({**job._planning_slot_values(), **values, 'state': 'published'})
            if job.job_state == 'new':
                job.with_context(om_fs_no_sync=True).job_state = 'planned'

    def _fs_sync_from_slots(self):
        """ Dates and technicians of the jobs from their planning slots (moved on the Gantt). """
        for job in self.filtered('is_field_service'):
            slots = job._fs_slots()
            if not slots:
                values = {'planned_start': False, 'planned_end': False}
                if job.job_state == 'planned':
                    values['job_state'] = 'new'
            else:
                resources = slots.resource_ids
                values = {
                    'planned_start': min(slots.mapped('start_datetime')),
                    'planned_end': max(slots.mapped('end_datetime')),
                    'technician_ids': [Command.set(resources.employee_id.ids)],
                }
                if job.job_state == 'new':
                    values['job_state'] = 'planned'
            job.with_context(om_fs_no_sync=True).write(values)

    def action_fs_plan(self):
        """ Open the planning assistant: free technicians suggested for the job. """
        self.ensure_one()
        if self.job_state in CLOSED_STATES:
            raise UserError(self.env._("The job %s is closed.", self.display_name))
        wizard = self.env['om.fs.plan.wizard'].with_context(default_task_id=self.id).create({})
        return wizard._fs_reopen()

    def action_fs_unplan(self):
        self.filtered(lambda j: j.job_state not in CLOSED_STATES).write({
            'planned_start': False, 'planned_end': False, 'job_state': 'new'})
        return True

    def action_view_fs_gantt(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_dispatch')
        action['context'] = {
            'om_fs_dispatch': True,
            'initialDate': fields.Datetime.to_string(self.planned_start) if self.planned_start else False,
            'search_default_group_resource': 1,
        }
        return action

    # ------------------------------------------------------------------
    # Work on site
    # ------------------------------------------------------------------

    def _fs_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _fs_my_employee(self):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(self.env._("Your user is not linked to an employee: ask your manager to create it."))
        return employee

    def _fs_check_open(self):
        for job in self:
            if job.job_state in CLOSED_STATES:
                raise UserError(self.env._("The job %s is closed.", job.display_name))

    def _fs_my_timers(self):
        return self.fs_timer_ids.filtered(lambda t: t.user_id == self.env.user)

    def _fs_start_timer(self, time_type):
        self.ensure_one()
        employee = self._fs_my_employee()
        # one running timer per technician, on all their jobs
        self.env['om.fs.timer'].sudo().search([('user_id', '=', self.env.uid)])._fs_stop()
        self.env['om.fs.timer'].sudo().create({
            'task_id': self.id,
            'user_id': self.env.uid,
            'employee_id': employee.id,
            'time_type': time_type,
        })

    def action_fs_start_travel(self):
        self._fs_check_open()
        for job in self:
            if job._fs_company().fs_travel_timesheet:
                job._fs_start_timer('travel')
            else:
                job._fs_my_timers()._fs_stop()
            job.job_state = 'travelling'
            job._fs_tracking_start()
            if job._fs_company().fs_notify_on_the_way:
                job._fs_notify_on_the_way()
        return True

    # ------------------------------------------------------------------
    # Live tracking
    # ------------------------------------------------------------------

    def _fs_tracking_start(self):
        """ The link of the tracking page, made when the technician leaves for the site. """
        for job in self.sudo():
            if job._fs_company().fs_live_tracking and not job.fs_track_token:
                job.fs_track_token = uuid.uuid4().hex

    def fs_mobile_set_position(self, latitude, longitude):
        """ Last position of the technician on the way, from the browser of their phone.

        :return: whether the job still wants the position (False: stop sharing it)
        """
        self.ensure_one()
        job = self.sudo()
        if job.job_state != 'travelling' or not job._fs_company().fs_live_tracking \
                or self.env.user not in job.technician_ids.user_id | job.user_ids:
            return False
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError):
            return True
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return True
        job.write({'fs_track_latitude': latitude, 'fs_track_longitude': longitude,
                   'fs_track_date': fields.Datetime.now()})
        return True

    def _fs_tracking_eta(self):
        """ Minutes to the site from the last position, at the average travel speed, or None. """
        self.ensure_one()
        job = self.sudo()
        site = job.site_partner_id or job.partner_id
        if job.job_state != 'travelling' or not job.fs_track_date or \
                not (site.partner_latitude or site.partner_longitude):
            return None
        km = _distance_km(job.fs_track_latitude, job.fs_track_longitude, site.partner_latitude, site.partner_longitude)
        speed = max(job._fs_company().fs_route_speed or 40.0, 1.0)
        return max(1, math.ceil(km / speed * 60))

    def action_fs_start_work(self):
        self._fs_check_open()
        for job in self:
            job._fs_start_timer('work')
            job.job_state = 'in_progress'
        return True

    def action_fs_pause_work(self):
        for job in self:
            job._fs_my_timers()._fs_stop()
        return True

    def action_fs_stop_work(self):
        return self.action_fs_pause_work()

    def action_fs_waiting_parts(self):
        self._fs_check_open()
        for job in self:
            job._fs_my_timers()._fs_stop()
            job.job_state = 'waiting_parts'
        return True

    def _fs_check_done(self):
        for job in self:
            if job.job_type_id.checklist_required:
                missing = job.checklist_line_ids.filtered(lambda l: l.required and not l.is_done)
                if missing:
                    raise UserError(self.env._(
                        "Fill in the checklist of %(job)s first: %(items)s",
                        job=job.display_name, items=', '.join(missing.mapped('name'))))
            if job.job_type_id.signature_required and not job.customer_signature:
                raise UserError(self.env._("The customer has to sign %s first.", job.display_name))

    def _fs_on_done(self):
        """ Hook called when the jobs are marked as done, before the report is sent. """
        return True

    def action_fs_done(self):
        self._fs_check_open()
        self._fs_check_done()
        self.fs_timer_ids._fs_stop()
        self.write({'job_state': 'done', 'date_done': fields.Datetime.now()})
        self._fs_on_done()
        for job in self:
            closed_stage = job.sudo().project_id.type_ids.filtered('fold')[:1]
            values = {'state': '1_done'}
            if closed_stage:
                values['stage_id'] = closed_stage.id
            job.with_context(om_fs_no_sync=True).write(values)
            if job._fs_company().fs_send_report:
                if job.partner_id.email:
                    job._fs_send_report()
                elif job.partner_id:
                    job._fs_notify_channels('report')
        return True

    def action_fs_cancel(self):
        self.fs_timer_ids._fs_stop()
        self.write({'job_state': 'cancelled'})
        self.with_context(om_fs_no_sync=True).write({'state': '1_canceled'})
        return True

    def action_fs_reset(self):
        for job in self:
            job.write({
                'job_state': 'planned' if job.planned_start else 'new',
                'date_done': False,
            })
            job.with_context(om_fs_no_sync=True).write({'state': '01_in_progress'})
        return True

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def _fs_notify_on_the_way(self):
        """ Tell the customer the technician is on the way: by email, and through the channels added
        by :meth:`_fs_notify_channels` (e.g. a messaging app). """
        self.ensure_one()
        if not self.partner_id:
            return False
        self._fs_notify_channels('on_the_way')
        if not self.partner_id.email:
            return False
        template = self.env.ref('om_field_service.mail_template_fs_on_the_way', raise_if_not_found=False)
        if not template:
            return False
        self.with_context(om_fs_technician=self.env.user.employee_id.name or self.env.user.name) \
            .message_post_with_source(template, message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def _fs_notify_channels(self, event):
        """ Hook to send a job event (``planned``, ``on_the_way``, ``report``) through another
        channel. """
        return False

    def _fs_send_report(self):
        self.ensure_one()
        template = self.env.ref('om_field_service.mail_template_fs_job_report', raise_if_not_found=False)
        if not template:
            return False
        self._fs_notify_channels('report')
        self.message_post_with_source(template, message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def action_fs_send_report(self):
        self.ensure_one()
        template = self.env.ref('om_field_service.mail_template_fs_job_report')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_model': 'project.task',
                'default_res_ids': self.ids,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'default_email_layout_xmlid': 'mail.mail_notification_light',
            },
        }

    def action_fs_open_job(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('om_field_service.project_task_view_form_fs').id, 'form')],
            'context': {'om_fs_job': True},
        }

    def _get_report_base_filename(self):
        self.ensure_one()
        return self.env._("Job Report - %s", self.job_number or self.name)

    def action_fs_print_report(self):
        return self.env.ref('om_field_service.action_report_fs_job').report_action(self)

    def action_fs_open_map(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'om_fs_map',
            'name': self.env._("Job Map"),
            'params': {'job_ids': self.ids},
        }

    def action_fs_geolocate(self):
        self.site_partner_id.geo_localize()
        return True

    # ------------------------------------------------------------------
    # Technician screen
    # ------------------------------------------------------------------

    def _fs_user_tz(self):
        return ZoneInfo(self.env.context.get('tz') or self.env.user.tz or 'UTC')

    @api.model
    def fs_mobile_jobs(self, day=None):
        """ Jobs of the current user for the day (local date ``YYYY-MM-DD``, today by default) and
        the jobs they are working on, ordered by time. """
        tz = self._fs_user_tz()
        local_day = fields.Date.to_date(day) if day else datetime.now(tz).date()
        start = datetime.combine(local_day, time.min, tz).astimezone(UTC).replace(tzinfo=None)
        stop = start + timedelta(days=1)
        mine = Domain('is_field_service', '=', True) & (
            Domain('user_ids', 'in', self.env.uid) | Domain('technician_ids.user_id', '=', self.env.uid))
        jobs = self.search(mine & (
            (Domain('planned_start', '<', stop) & Domain('planned_end', '>', start)
             & Domain('job_state', '!=', 'cancelled'))
            | Domain('job_state', 'in', ACTIVE_STATES)
        ))
        jobs = jobs.sorted(lambda j: (j.planned_start or datetime.max, j.id))
        employee = self.env.user.employee_id
        return {
            'day': fields.Date.to_string(local_day),
            'jobs': [job._fs_mobile_summary() for job in jobs],
            'route_url': jobs._fs_route_url(employee) if employee else False,
            'can_optimise': bool(employee.sudo().is_technician) and len(jobs.filtered('planned_start')) > 1,
        }

    def _fs_route_url(self, employee):
        """ Maps link of the route of the technician through these jobs, in their planned order,
        from their start address. """
        start = employee._fs_route_start_partner()
        points = []
        for partner in [start] + [job.site_partner_id or job.partner_id
                                  for job in self.filtered('planned_start').sorted('planned_start')]:
            if partner and (partner.partner_latitude or partner.partner_longitude):
                points.append((partner.partner_latitude, partner.partner_longitude))
        return maps_route_url(points)

    @api.model
    def fs_mobile_optimise_action(self, day=None):
        """ Open the route optimisation of the current user for the day. """
        employee = self._fs_my_employee()
        wizard = self.env['om.fs.route.wizard'].create({
            'employee_id': employee.id,
            'date': fields.Date.to_date(day) if day else fields.Date.context_today(self),
        })
        return wizard._fs_reopen()

    def _fs_dt(self, value):
        return fields.Datetime.to_string(value) if value else False

    def _fs_mobile_summary(self):
        self.ensure_one()
        partner = self.site_partner_id or self.partner_id
        return {
            'id': self.id,
            'number': self.job_number or '',
            'name': self.name,
            'customer': self.partner_id.commercial_partner_id.name or '',
            'site': partner.name or '',
            'address': self.site_address or '',
            'start': self._fs_dt(self.planned_start),
            'end': self._fs_dt(self.planned_end),
            'state': self.job_state,
            'state_label': dict(self._fields['job_state']._description_selection(self.env))[self.job_state],
            'priority': self.priority,
            'job_type': self.job_type_id.name or '',
            'timer': self.fs_my_timer or False,
        }

    def _fs_mobile_data(self):
        """ Everything the phone screen shows of the job. Override to add sections (``extra``). """
        self.ensure_one()
        partner = self.site_partner_id or self.partner_id
        data = self._fs_mobile_summary()
        data.update({
            'phone': partner.phone or self.partner_id.phone or self.partner_phone or '',
            'email': self.partner_id.email or '',
            'contact': partner.name if partner != self.partner_id.commercial_partner_id else '',
            'nav': partner._fs_map_urls() if partner else {},
            'instructions': self.job_type_id.description or '',
            'description': html2plaintext(self.description or '').strip(),
            'equipment': self.site_equipment or '',
            'timer_start': self._fs_dt(self.fs_my_timer_start),
            'travel_hours': self.travel_hours,
            'work_hours': self.work_hours,
            'checklist': self.checklist_line_ids._fs_mobile_data(),
            'notes': html2plaintext(self.work_summary or '').strip(),
            'photos': [{'id': photo.id, 'name': photo.name} for photo in self.photo_ids],
            'signed': bool(self.customer_signature),
            'signed_by': self.signed_by or '',
            'signed_on': self._fs_dt(self.signed_on),
            'signature_required': self.job_type_id.signature_required,
            'technicians': ', '.join(self.technician_ids.mapped('name')),
            'closed': self.job_state in CLOSED_STATES,
            'can_travel': self._fs_company().fs_travel_timesheet,
            'tracking': self.job_state == 'travelling' and self._fs_company().fs_live_tracking,
            'extra': {},
        })
        return data

    def fs_mobile_job(self):
        self.ensure_one()
        return self._fs_mobile_data()

    def fs_mobile_action(self, action):
        """ Run a button of the phone screen and return the job data. """
        self.ensure_one()
        actions = {
            'start_travel': self.action_fs_start_travel,
            'start_work': self.action_fs_start_work,
            'pause_work': self.action_fs_pause_work,
            'stop_work': self.action_fs_stop_work,
            'waiting_parts': self.action_fs_waiting_parts,
            'done': self.action_fs_done,
        }
        if action not in actions:
            raise UserError(self.env._("Unknown action."))
        actions[action]()
        return self._fs_mobile_data()

    def fs_mobile_set_notes(self, notes):
        self.ensure_one()
        self.work_summary = plaintext2html(notes or '')
        return True

    def fs_mobile_add_photo(self, name, data):
        """ Add a photo taken on site (base64 content). """
        self.ensure_one()
        self._fs_check_open()
        attachment = self.env['ir.attachment'].create({
            'name': name or self.env._("Photo"),
            'raw': base64.b64decode(data or b''),
            'res_model': 'project.task',
            'res_id': self.id,
        })
        if not (attachment.mimetype or '').startswith('image/'):
            attachment.unlink()
            raise UserError(self.env._("Only pictures can be added as photos."))
        self.photo_ids = [Command.link(attachment.id)]
        return self._fs_mobile_data()

    def fs_mobile_remove_photo(self, attachment_id):
        self.ensure_one()
        self._fs_check_open()
        photo = self.photo_ids.filtered(lambda p: p.id == attachment_id)
        self.photo_ids = [Command.unlink(attachment_id)]
        photo.unlink()
        return self._fs_mobile_data()

    def fs_mobile_sign(self, name, signature):
        """ Save the signature of the customer (base64 PNG, without the data URL prefix). """
        self.ensure_one()
        self._fs_check_open()
        if not signature:
            raise UserError(self.env._("The signature is empty."))
        self.write({
            'customer_signature': signature,
            'signed_by': name or self.partner_id.name,
            'signed_on': fields.Datetime.now(),
        })
        self.message_post(body=self.env._("Signed on site by %s.", self.signed_by))
        return self._fs_mobile_data()

    def fs_mobile_send_report(self):
        self.ensure_one()
        if not self.partner_id.email:
            raise UserError(self.env._("The customer has no email address."))
        self._fs_send_report()
        return True

    # ------------------------------------------------------------------
    # Map
    # ------------------------------------------------------------------

    @api.model
    def fs_map_data(self, period='today', employee_id=False, job_ids=None):
        """ Jobs shown on the map.

        :param str period: ``today``, ``tomorrow``, ``week`` (the next 7 days) or ``open`` (every
            job not closed)
        :param int employee_id: only the jobs of this technician
        :param list job_ids: only these jobs (the other filters are ignored)
        """
        domain = Domain('is_field_service', '=', True)
        if job_ids:
            domain &= Domain('id', 'in', job_ids)
        else:
            tz = self._fs_user_tz()
            today = datetime.now(tz).date()
            if period in ('today', 'tomorrow', 'week'):
                first = today + timedelta(days=1 if period == 'tomorrow' else 0)
                days = 7 if period == 'week' else 1
                start = datetime.combine(first, time.min, tz).astimezone(UTC).replace(tzinfo=None)
                stop = start + timedelta(days=days)
                domain &= Domain('planned_start', '<', stop) & Domain('planned_end', '>', start) \
                    & Domain('job_state', '!=', 'cancelled')
            else:
                domain &= Domain('job_state', 'not in', CLOSED_STATES)
            if employee_id:
                domain &= Domain('technician_ids', 'in', [employee_id])
        jobs = self.search(domain, limit=500)
        jobs = jobs.sorted(lambda j: (j.planned_start or datetime.max, j.id))
        technicians = self.env['hr.employee'].search(
            [('is_technician', '=', True), ('company_id', 'in', self.env.companies.ids + [False])])
        return {
            'jobs': [job._fs_map_values() for job in jobs],
            'technicians': [{'id': employee.id, 'name': employee.name} for employee in technicians],
        }

    def _fs_map_values(self):
        self.ensure_one()
        partner = self.site_partner_id or self.partner_id
        located = bool(partner.partner_latitude or partner.partner_longitude)
        return {
            **self._fs_mobile_summary(),
            'lat': partner.partner_latitude if located else False,
            'lng': partner.partner_longitude if located else False,
            'technicians': ', '.join(self.technician_ids.mapped('name')),
            'technician_ids': self.technician_ids.ids,
            'directions': partner._fs_map_urls().get('google', '') if partner else '',
        }

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------

    @api.model
    def _fs_demo_plan(self):
        """ Demo data: plan the demo jobs around today, in the timezone of their technicians, and
        close a job of last week with its time, checklist and work done. """
        plans = [
            ('om_field_service.job_bayview', 0, 9, 1.5),
            ('om_field_service.job_sunset_thermostat', 0, 10.5, 1),
            ('om_field_service.job_harbor', 0, 13, 2),
            ('om_field_service.job_hills_softener', 0, 15.5, 1),
            ('om_field_service.job_sunset', 1, 9, 3),
            ('om_field_service.job_bayview_old', -7, 10, 2),
        ]
        today = fields.Date.context_today(self)
        for xmlid, days, hour, duration in plans:
            job = self.env.ref(xmlid, raise_if_not_found=False)
            if not job:
                continue
            tz = ZoneInfo(job.technician_ids[:1].resource_id.tz or self.env.user.tz or 'UTC')
            start = datetime.combine(today + timedelta(days=days), time(int(hour), int(hour % 1 * 60)), tz)
            start = start.astimezone(UTC).replace(tzinfo=None)
            job.write({'planned_start': start, 'planned_end': start + timedelta(hours=duration)})
        old = self.env.ref('om_field_service.job_bayview_old', raise_if_not_found=False)
        if old and old.job_state != 'done':
            employee = old.technician_ids[:1]
            day = old.planned_start.date()
            self.env['account.analytic.line'].create([{
                'name': self.env._("Travel to %s", old.site_partner_id.display_name),
                'task_id': old.id, 'project_id': old.project_id.id, 'employee_id': employee.id,
                'date': day, 'unit_amount': 0.5, 'fs_time_type': 'travel',
            }, {
                'name': self.env._("Valve replaced and system bled"),
                'task_id': old.id, 'project_id': old.project_id.id, 'employee_id': employee.id,
                'date': day, 'unit_amount': 1.75, 'fs_time_type': 'work',
            }])
            for line in old.checklist_line_ids:
                if line.check_type == 'check':
                    line.value_check = True
                elif line.check_type == 'text':
                    line.value_text = self.env._("Valve seized by limescale")
            old.write({
                'work_summary': plaintext2html(self.env._(
                    "Replaced the thermostatic valve of the meeting room radiator, bled the system and "
                    "checked the pressure.")),
                'signed_by': old.partner_id.name,
                'signed_on': old.planned_end,
                'job_state': 'done',
                'date_done': old.planned_end,
                'state': '1_done',
            })
