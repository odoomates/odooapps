from odoo import models


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    def _planning_leave_message(self, resource, leaves):
        """ Name the type of the time off rather than the generic text of its resource leave. """
        time_off = leaves.holiday_id
        if not time_off:
            return super()._planning_leave_message(resource, leaves)
        names = ', '.join(time_off.work_entry_type_id.mapped('name'))
        others = leaves.filtered(lambda leave: not leave.holiday_id)
        if others:
            names = ', '.join([names] + [name for name in others.mapped('name') if name])
        return self.env._("%(resource)s is on time off: %(type)s", resource=resource.name, type=names)

    def _planning_check(self):
        """ Time off still to approve is a conflict too. """
        result = super()._planning_check()
        slots = self.filtered(lambda s: s.start_datetime and s.end_datetime and s.resource_ids)
        if not slots:
            return result
        resources = slots.resource_ids._origin
        employees = resources.sudo().employee_id
        if not employees:
            return result
        pending = self.env['hr.leave'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('state', 'in', ('confirm', 'validate1')),
            ('date_from', '<', max(slots.mapped('end_datetime'))),
            ('date_to', '>', min(slots.mapped('start_datetime'))),
        ])
        if not pending:
            return result
        for slot in slots:
            for leave in pending:
                resource = leave.employee_id.resource_id
                if resource in slot.resource_ids._origin and leave.date_from < slot.end_datetime \
                        and leave.date_to > slot.start_datetime:
                    result[slot.id].append({
                        'type': 'time_off_pending', 'resource_id': resource.id,
                        'message': self.env._(
                            "%(resource)s asked for time off (%(type)s), still to approve",
                            resource=resource.name, type=leave.work_entry_type_id.name),
                    })
        return result

