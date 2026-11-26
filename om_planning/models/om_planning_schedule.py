import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_datetime


class OmPlanningSchedule(models.Model):
    _name = 'om.planning.schedule'
    _description = "Planning Schedule"
    _inherit = ['mail.thread']
    _order = 'start_datetime desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, string="Name")
    start_datetime = fields.Datetime(string="From", required=True,
                                     default=lambda self: self._default_period()[0])
    end_datetime = fields.Datetime(string="To", required=True,
                                   default=lambda self: self._default_period()[1])
    resource_ids = fields.Many2many(
        'resource.resource', string="Only These Resources",
        help="Leave empty to publish the slots of every resource.")
    role_ids = fields.Many2many('om.planning.role', string="Only These Roles")
    include_open_slots = fields.Boolean(string="Include Open Slots", default=True)
    send_email = fields.Boolean(string="Send by Email", default=True)
    note = fields.Text(string="Message")
    slot_ids = fields.Many2many('om.planning.slot', string="Slots", readonly=True)
    slot_count = fields.Integer(compute='_compute_slot_count', string="Number of Slots")
    recipient_ids = fields.Many2many('res.partner', string="Sent To", readonly=True)
    access_token = fields.Char(copy=False, readonly=True, groups='om_planning.group_planning_manager')
    state = fields.Selection([('draft', 'Draft'), ('sent', 'Sent')], default='draft', required=True,
                             tracking=True, string="Status")
    sent_date = fields.Datetime(string="Sent On", readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string="Company", required=True,
                                 default=lambda self: self.env.company)

    def _default_period(self):
        tz = ZoneInfo(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return (monday.astimezone(UTC).replace(tzinfo=None),
                (monday + timedelta(days=7)).astimezone(UTC).replace(tzinfo=None))

    @api.depends('start_datetime', 'end_datetime')
    def _compute_name(self):
        for schedule in self:
            if schedule.start_datetime and schedule.end_datetime:
                schedule.name = self.env._(
                    "Schedule %(start)s - %(end)s",
                    start=format_datetime(self.env, schedule.start_datetime, dt_format='short').split(' ')[0],
                    end=format_datetime(self.env, schedule.end_datetime - timedelta(seconds=1),
                                        dt_format='short').split(' ')[0])
            else:
                schedule.name = self.env._("Schedule")

    @api.depends('slot_ids')
    def _compute_slot_count(self):
        for schedule in self:
            schedule.slot_count = len(schedule.slot_ids)

    def _get_slot_domain(self):
        self.ensure_one()
        domain = Domain([
            ('start_datetime', '<', self.end_datetime),
            ('end_datetime', '>', self.start_datetime),
            ('company_id', '=', self.company_id.id),
        ])
        resource_domain = Domain('resource_ids', '!=', False)
        if self.resource_ids:
            resource_domain = Domain('resource_ids', 'in', self.resource_ids.ids)
        if self.include_open_slots:
            resource_domain |= Domain('resource_ids', '=', False)
        domain &= resource_domain
        if self.role_ids:
            domain &= Domain('role_id', 'in', self.role_ids.ids)
        return domain

    def _get_access_token(self):
        self.ensure_one()
        schedule = self.sudo()
        if not schedule.access_token:
            schedule.access_token = uuid.uuid4().hex
        return schedule.access_token

    def _get_resource_url(self, resource):
        self.ensure_one()
        return '%s/planning/schedule/%s/%s' % (
            self.get_base_url(), self._get_access_token(), resource._planning_get_access_token())

    def _get_ics_url(self, resource):
        return '%s/planning/ics/%s.ics' % (self.get_base_url(), resource._planning_get_access_token())

    def planning_resource_slots(self, resource_id):
        """ Slots of the schedule for a resource (used by the email). """
        self.ensure_one()
        return self.slot_ids.filtered(lambda s: resource_id in s.resource_ids.ids).sorted('start_datetime')

    def planning_open_slots(self, resource_id=None):
        """ Open slots of the schedule, those of the roles of the resource when given. """
        self.ensure_one()
        slots = self.slot_ids.filtered('is_open')
        if resource_id:
            roles = self.env['resource.resource'].sudo().browse(resource_id).planning_role_ids
            if roles:
                slots = slots.filtered(lambda s: not s.role_id or s.role_id in roles)
        return slots.sorted('start_datetime')

    def planning_format_slot(self, slot, resource_id=None):
        """ Human text of a slot in the timezone of the resource. """
        resource = self.env['resource.resource'].sudo().browse(resource_id) if resource_id else None
        tz = ZoneInfo((resource and resource.tz) or self.env.user.tz or 'UTC')
        start = slot.start_datetime.replace(tzinfo=UTC).astimezone(tz)
        end = slot.end_datetime.replace(tzinfo=UTC).astimezone(tz)
        end_text = end.strftime('%H:%M') if end.date() == start.date() else end.strftime('%a %d %b %H:%M')
        return f"{start.strftime('%a %d %b %H:%M')} - {end_text}"

    def action_send(self):
        for schedule in self:
            slots = self.env['om.planning.slot'].search(schedule._get_slot_domain())
            if not slots:
                raise UserError(self.env._("There is no slot to publish in this period."))
            slots.action_publish()
            schedule.write({'slot_ids': [(6, 0, slots.ids)], 'state': 'sent', 'sent_date': fields.Datetime.now()})
            schedule._get_access_token()
            if schedule.send_email:
                schedule._send_emails()
            schedule.message_post(body=self.env._("%s slots published.", len(slots)))
        if len(self) == 1 and self.env.context.get('om_planning_from_gantt'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': self.env._("%s slots published and sent.", len(self.slot_ids)),
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        return True

    def _send_emails(self):
        self.ensure_one()
        template = self.env.ref('om_planning.mail_template_planning_schedule', raise_if_not_found=False)
        if not template:
            return
        resources = self.slot_ids.resource_ids
        if self.resource_ids:
            resources &= self.resource_ids
        open_slots = self.slot_ids.filtered('is_open') if self.include_open_slots else self.slot_ids.browse()
        if open_slots:
            # people who can take an open slot get the schedule too: those with its role, or
            # anybody with a planning role for the open slots without role
            role_domain = Domain('planning_role_ids', 'in', open_slots.role_id.ids)
            if any(not slot.role_id for slot in open_slots):
                role_domain |= Domain('planning_role_ids', '!=', False)
            candidates = self.env['resource.resource'].search(Domain([
                ('resource_type', '=', 'user'),
                ('company_id', 'in', [self.company_id.id, False]),
            ]) & role_domain)
            if self.resource_ids:
                candidates &= self.resource_ids
            resources |= candidates
        recipients = self.env['res.partner']
        for resource in resources.filtered(lambda r: r.resource_type == 'user'):
            partner = resource._planning_get_partner()
            if not partner or not partner.email:
                continue
            template.with_context(
                planning_resource_id=resource.id,
                planning_resource_name=resource.name,
                planning_url=self._get_resource_url(resource),
                planning_ics_url=self._get_ics_url(resource),
                lang=partner.lang,
            ).send_mail(self.id, email_values={'recipient_ids': [(4, partner.id)]})
            recipients |= partner
        self.recipient_ids = [(6, 0, recipients.ids)]

    def action_view_slots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_slot')
        action['domain'] = [('id', 'in', self.slot_ids.ids)]
        action['views'] = [(False, 'list'), (False, 'form')]
        action['view_mode'] = 'list,form'
        return action
