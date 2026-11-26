from markupsafe import Markup

from odoo import fields, models
from odoo.fields import Command


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _validate_leave_request(self):
        res = super()._validate_leave_request()
        self._planning_apply_time_off_policy()
        return res

    def _planning_overlapping_slots(self):
        """ Slots of the employee of the time off that overlap it and are not over yet. """
        self.ensure_one()
        resource = self.employee_id.resource_id
        if not resource or not self.date_from or not self.date_to:
            return self.env['om.planning.slot']
        return self.env['om.planning.slot'].sudo().search([
            ('resource_ids', 'in', resource.ids),
            ('start_datetime', '<', self.date_to),
            ('end_datetime', '>', self.date_from),
            ('end_datetime', '>', fields.Datetime.now()),
        ])

    def _planning_apply_time_off_policy(self):
        for leave in self.sudo().filtered('employee_id'):
            policy = leave.employee_id.company_id.planning_time_off_policy or 'warn'
            if policy == 'keep':
                continue
            slots = leave._planning_overlapping_slots()
            if not slots:
                continue
            labels = [slot._planning_short_label(leave.employee_id.resource_id) for slot in slots]
            if policy == 'unassign':
                slots.write({'resource_ids': [Command.unlink(leave.employee_id.resource_id.id)]})
                body = self.env._(
                    "%(employee)s is on time off: they were removed from %(count)s slot(s), to plan again:",
                    employee=leave.employee_id.name, count=len(slots))
            else:
                body = self.env._(
                    "%(employee)s is on time off and still planned on %(count)s slot(s):",
                    employee=leave.employee_id.name, count=len(slots))
            leave._planning_notify_planners(body, labels)

    def _planning_notify_planners(self, body, labels):
        self.ensure_one()
        planners = self.env.ref('om_planning.group_planning_manager').sudo().all_user_ids.filtered(
            lambda u: not u.share and u.active and self.employee_id.company_id in u.company_ids)
        planners |= self.employee_id.resource_id._planning_get_manager_users()
        partners = planners.partner_id - self.env.ref('base.partner_root')
        if not partners:
            return
        items = Markup('').join(Markup('<li>%s</li>') % label for label in labels)
        self.message_notify(
            partner_ids=partners.ids,
            subject=self.env._("Planning: %s is on time off", self.employee_id.name),
            body=Markup('<p>%s</p><ul>%s</ul>') % (body, items),
        )
