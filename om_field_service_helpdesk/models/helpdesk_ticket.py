from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from odoo.addons.om_field_service.models.project_task import CLOSED_STATES, JOB_STATES


class OmHelpdeskTicket(models.Model):
    _inherit = 'om.helpdesk.ticket'

    use_field_service = fields.Boolean(related='team_id.use_field_service', string="Team Uses Field Service")
    fs_equipment = fields.Text(
        string="Equipment", help="Equipment to look at on site: model, serial number, where it is.")
    fs_job_ids = fields.One2many('project.task', 'helpdesk_ticket_id', string="Field Service Jobs")
    fs_job_count = fields.Integer(compute='_compute_fs_job', string="Job Count")
    fs_job_state = fields.Selection(
        JOB_STATES, compute='_compute_fs_job', string="Job Status",
        help="Status of the open field service job of the ticket, else of its last job.")
    fs_job_done_id = fields.Many2one('project.task', compute='_compute_fs_job', string="Done Job")

    @api.depends('fs_job_ids.job_state')
    def _compute_fs_job(self):
        for ticket in self:
            jobs = ticket.sudo().fs_job_ids.sorted('id')
            current = jobs.filtered(lambda j: j.job_state not in CLOSED_STATES)[-1:] or jobs[-1:]
            ticket.fs_job_count = len(jobs)
            ticket.fs_job_state = current.job_state or False
            ticket.fs_job_done_id = jobs.filtered(lambda j: j.job_state == 'done')[-1:].with_env(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        tickets.filtered(lambda t: t._fs_auto_create())._fs_create_job()
        return tickets

    def write(self, vals):
        res = super().write(vals)
        if 'ticket_type_id' in vals or 'team_id' in vals:
            self.filtered(lambda t: not t.fs_job_ids and t._fs_auto_create())._fs_create_job()
        return res

    def _fs_auto_create(self):
        self.ensure_one()
        team = self.team_id
        return bool(team.use_field_service and not self.is_closed
                    and (team.fs_auto_create or self.ticket_type_id.fs_create_job))

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def _fs_project(self):
        self.ensure_one()
        project = self.team_id.fs_project_id
        if not project:
            project = self.env['project.project'].sudo().search(
                [('is_field_service', '=', True), ('company_id', 'in', [self.company_id.id, False])], limit=1)
        if not project:
            raise UserError(self.env._("Create a field service project first."))
        return project

    def _fs_job_values(self):
        """ Values of the job made from the ticket. """
        self.ensure_one()
        job_type = self.ticket_type_id.fs_job_type_id or self.team_id.fs_job_type_id
        values = {
            'name': self.name,
            'project_id': self._fs_project().id,
            'partner_id': self.partner_id.id,
            'helpdesk_ticket_id': self.id,
            'description': self.description,
            'site_equipment': self.fs_equipment or False,
            'priority': self.priority or '0',
            'company_id': (self.company_id or self.env.company).id,
        }
        if self.partner_phone:
            values['partner_phone'] = self.partner_phone
        if job_type:
            values['job_type_id'] = job_type.id
        return values

    def _fs_create_job(self):
        """ Create the field service job of each ticket. """
        jobs = self.env['project.task']
        for ticket in self:
            if not ticket.partner_id:
                raise UserError(self.env._("Set the customer of %s first.", ticket.display_name))
            job = self.env['project.task'].sudo().with_context(mail_create_nolog=True).create(
                ticket._fs_job_values())
            jobs |= job
            ticket.message_post(body=Markup(self.env._("Field service job %s created.")) % job._get_html_link(
                title=job.job_number or job.name))
        return jobs.with_env(self.env)

    def action_fs_create_job(self):
        self.ensure_one()
        if not self.use_field_service:
            raise UserError(self.env._("The team of %s does not use field service.", self.display_name))
        job = self._fs_create_job()
        return job.action_fs_open_job()

    def action_fs_view_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('helpdesk_ticket_id', '=', self.id)]
        action['context'] = {'om_fs_job': True, 'default_helpdesk_ticket_id': self.id,
                             'default_partner_id': self.partner_id.id}
        if len(self.fs_job_ids) == 1:
            action['views'] = [(self.env.ref('om_field_service.project_task_view_form_fs').id, 'form')]
            action['res_id'] = self.fs_job_ids.id
        return action

    def action_fs_print_report(self):
        self.ensure_one()
        if not self.fs_job_done_id:
            raise UserError(self.env._("No job of %s is done yet.", self.display_name))
        return self.fs_job_done_id.sudo().action_fs_print_report()

    # ------------------------------------------------------------------
    # The job is done
    # ------------------------------------------------------------------

    def _fs_job_done(self, job):
        """ Tell the ticket that ``job`` is done: message with the report, and close the ticket when
        the team says so and every job is closed. """
        self.ensure_one()
        team = self.team_id
        mode = team.fs_done_message if team else 'note'
        if mode != 'none':
            report = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'om_field_service.action_report_fs_job', job.ids)[0]
            name = '%s.pdf' % job._get_report_base_filename()
            summary = html2plaintext(job.work_summary or '').strip()
            body = Markup('<p>%s</p>') % self.env._(
                "The field service job %(job)s is done.", job=job.job_number or job.name)
            if summary:
                body += Markup('<p>%s</p>') % summary
            if mode == 'customer':
                body += Markup('<p>%s <a href="%s">%s</a></p>') % (
                    self.env._("Report:"), f'{job.get_base_url()}/my/field_service/{job.id}',
                    self.env._("view it in your portal"))
            self.message_post(
                body=body,
                attachments=[(name, report)],
                message_type='comment',
                subtype_xmlid='mail.mt_comment' if mode == 'customer' else 'mail.mt_note',
            )
        if team.fs_close_ticket and not self.is_closed and \
                all(j.job_state in CLOSED_STATES for j in self.sudo().fs_job_ids):
            if self._get_closing_stage():
                self.action_close()
