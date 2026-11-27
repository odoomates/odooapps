import logging

from odoo import api, fields, models
from odoo.fields import Command, Domain

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    fs_subscription_job_ids = fields.One2many('project.task', 'fs_subscription_id', string="Contract Jobs")
    fs_subscription_job_count = fields.Integer(compute='_compute_fs_subscription_job_count',
                                               string="Contract Job Count")
    fs_technician_id = fields.Many2one(
        'hr.employee', string="Preferred Technician", domain="[('is_technician', '=', True)]",
        help="Technician of the maintenance visits of this subscription. Empty: the one of the product.")
    fs_has_maintenance = fields.Boolean(compute='_compute_fs_has_maintenance', string="Has Maintenance Visits")

    @api.depends('fs_subscription_job_ids')
    def _compute_fs_subscription_job_count(self):
        for order in self:
            order.fs_subscription_job_count = len(order.fs_subscription_job_ids)

    @api.depends('order_line.product_id.fs_maintenance', 'is_subscription')
    def _compute_fs_has_maintenance(self):
        for order in self:
            order.fs_has_maintenance = order.is_subscription and any(order.order_line.mapped('fs_maintenance'))

    def _subscription_start(self):
        res = super()._subscription_start()
        for order in self:
            for line in order.order_line.filtered(lambda l: l.fs_maintenance and not l.fs_next_job_date):
                line.fs_next_job_date = order.subscription_start_date
        self._fs_create_due_jobs()
        return res

    # ------------------------------------------------------------------
    # Maintenance visits
    # ------------------------------------------------------------------

    def _fs_covers(self, job_only=False):
        """ Whether the subscription covers the field service work: its visits (``job_only``) or
        every job of the customer. """
        self.ensure_one()
        if self.subscription_state not in ('progress', 'paused'):
            return False
        coverages = set(self.order_line.filtered('fs_maintenance').product_id.mapped('fs_coverage'))
        return bool(coverages & ({'contract', 'all'} if job_only else {'all'}))

    def _fs_visit_delta(self, line):
        self.ensure_one()
        return self.subscription_plan_id._get_billing_delta() * max(line.product_id.fs_job_interval, 1)

    def _fs_job_values(self, line, due):
        self.ensure_one()
        product = line.product_id
        technician = self.fs_technician_id or product.fs_technician_id
        project = self.env['project.project'].sudo().search(
            [('is_field_service', '=', True), ('company_id', 'in', [self.company_id.id, False])], limit=1)
        values = {
            'name': self.env._("%(product)s: maintenance visit", product=product.name),
            'project_id': project.id,
            'partner_id': self.partner_id.id,
            'site_partner_id': self.partner_shipping_id.id,
            'date_deadline': due,
            'fs_subscription_id': self.id,
            'company_id': self.company_id.id,
            'description': line.name,
        }
        if product.fs_job_type_id:
            values['job_type_id'] = product.fs_job_type_id.id
        if technician:
            values['technician_ids'] = [Command.set(technician.ids)]
        return values

    def _fs_create_due_jobs(self, today=None):
        """ Create the jobs of the maintenance visits due soon. Visits missed long ago (a contract
        started in the past) are skipped: the last one due is created. """
        today = today or fields.Date.context_today(self)
        Task = self.env['project.task'].sudo()
        all_jobs = Task
        for order in self.filtered(lambda o: o.is_subscription and o.subscription_state == 'progress'):
            jobs = Task
            for line in order.order_line.filtered(lambda l: l.fs_maintenance and l.fs_next_job_date):
                delta = order._fs_visit_delta(line)
                lead = line.product_id.fs_lead_days
                due = line.fs_next_job_date
                while due + delta <= today:
                    due += delta
                while due and fields.Date.subtract(due, days=lead) <= today:
                    if order.subscription_end_date and due > order.subscription_end_date:
                        due = False
                        break
                    jobs |= Task.create(order._fs_job_values(line, due))
                    due += delta
                line.fs_next_job_date = due
            if jobs:
                order.message_post(body=self.env._(
                    "Maintenance visits to plan: %s", ', '.join(jobs.mapped(lambda j: j.job_number or j.name))))
            all_jobs |= jobs
        return all_jobs.with_env(self.env)

    @api.model
    def _cron_fs_subscription_jobs(self):
        orders = self.search(Domain('is_subscription', '=', True) & Domain('subscription_state', '=', 'progress')
                             & Domain('order_line.fs_next_job_date', '!=', False))
        for order in orders:
            try:
                with self.env.cr.savepoint():
                    order._fs_create_due_jobs()
            except Exception:  # noqa: BLE001
                _logger.exception("Subscription %s: maintenance jobs not created", order.name)

    def action_fs_create_due_jobs(self):
        jobs = self._fs_create_due_jobs()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if jobs else 'info',
                'message': self.env._("%s maintenance jobs created.", len(jobs)) if jobs else
                self.env._("No maintenance visit is due yet."),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_fs_view_subscription_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('fs_subscription_id', '=', self.id)]
        action['context'] = {'om_fs_job': True, 'default_fs_subscription_id': self.id,
                             'default_partner_id': self.partner_id.id}
        return action
