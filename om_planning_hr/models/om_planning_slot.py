from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.fields import Domain


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    employee_ids = fields.Many2many('hr.employee', compute='_compute_employee_ids', string="Employees")
    department_id = fields.Many2one(
        'hr.department', compute='_compute_department_id', store=True, index='btree_not_null',
        string="Department", help="Department of the first employee of the slot.")

    @api.depends('resource_ids')
    def _compute_employee_ids(self):
        for slot in self:
            slot.employee_ids = slot.resource_ids._origin.sudo().employee_id

    @api.depends('resource_ids.employee_id.department_id')
    def _compute_department_id(self):
        for slot in self:
            employees = slot.resource_ids._origin.sudo().employee_id
            slot.department_id = employees[:1].department_id

    @api.model
    def _planning_expand_resource_domain(self):
        """ Every employee shows on the Gantt, also without planning role. """
        return super()._planning_expand_resource_domain() | Domain([
            ('employee_id', '!=', False),
            ('company_id', 'in', self.env.companies.ids),
        ])

    def _group_expand_resource_ids(self, resources, domain):
        if self._planning_expand_filtered(domain, ('department_id',)):
            return resources
        return super()._group_expand_resource_ids(resources, domain)

    @api.model
    def _planning_hr_demo(self):
        """ Demo data: the planning resource of the demo user becomes their employee, and the
        cashiers of the demo employees get a week of shifts. """
        employee = self.env.ref('hr.employee_qdp', raise_if_not_found=False)
        resource = self.env.ref('om_planning.resource_mark', raise_if_not_found=False)
        if employee and resource and resource.active:
            employee.resource_id.write({
                'planning_role_ids': [fields.Command.set(resource.planning_role_ids.ids)],
                'planning_default_role_id': resource.planning_default_role_id.id,
            })
            slots = self.search([('resource_ids', 'in', resource.ids)])
            slots.with_context(om_planning_keep_published=True).write({
                'resource_ids': [fields.Command.unlink(resource.id), fields.Command.link(employee.resource_id.id)],
            })
            resource.write({'active': False, 'user_id': False})
        morning = self.env.ref('om_planning.template_morning', raise_if_not_found=False)
        evening = self.env.ref('om_planning.template_evening', raise_if_not_found=False)
        if not (morning and evening):
            return
        today = fields.Date.context_today(self)
        monday = today + relativedelta(days=-today.weekday(), weeks=1)
        values_list = []
        for xmlid, templates in (('hr.employee_hne', (morning, morning, evening, evening)),
                                 ('hr.employee_jep', (evening, evening, morning, morning))):
            cashier = self.env.ref(xmlid, raise_if_not_found=False)
            if not cashier:
                continue
            tz = cashier.resource_id.tz or 'UTC'
            for index, template in enumerate(templates):
                start, stop = template._get_period(monday + relativedelta(days=index), tz)
                values_list.append({
                    'resource_ids': [fields.Command.set(cashier.resource_id.ids)],
                    'role_id': template.role_id.id,
                    'template_id': template.id,
                    'start_datetime': start,
                    'end_datetime': stop,
                    'break_hours': template.break_hours,
                    'state': 'published' if index < 2 else 'draft',
                })
        self.create(values_list)
