from odoo import api, fields, models
from odoo.fields import Domain


class ProjectTask(models.Model):
    _inherit = 'project.task'

    fs_subscription_id = fields.Many2one(
        'sale.order', string="Maintenance Contract", index='btree_not_null', copy=False, tracking=True,
        domain="[('is_subscription', '=', True), ('subscription_state', 'in', ('progress', 'paused')), "
               "('partner_id', 'child_of', commercial_partner_id)]",
        help="Subscription this job belongs to: its visits, or work it covers.")

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        for job in tasks.filtered('is_field_service'):
            if not job.fs_subscription_id and job.partner_id:
                contract = job._fs_covering_subscription()
                if contract:
                    job.fs_subscription_id = contract
            job._fs_apply_contract_coverage()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if vals.get('fs_subscription_id'):
            for job in self.filtered('is_field_service'):
                job._fs_apply_contract_coverage()
        return res

    @api.onchange('partner_id')
    def _onchange_partner_fs_subscription(self):
        if self.is_field_service and self.partner_id and not self.fs_subscription_id:
            self.fs_subscription_id = self._fs_covering_subscription()

    @api.onchange('fs_subscription_id')
    def _onchange_fs_subscription_id(self):
        if self.fs_subscription_id and self.fs_subscription_id._fs_covers(job_only=True):
            self.is_covered = True
            self.coverage = 'contract'

    def _fs_covering_subscription(self):
        """ Running subscription of the customer that covers every job. """
        self.ensure_one()
        contracts = self.env['sale.order'].sudo().search(
            Domain('is_subscription', '=', True) & Domain('subscription_state', 'in', ('progress', 'paused'))
            & Domain('partner_id', 'child_of', self.partner_id.commercial_partner_id.id)
            & Domain('order_line.product_id.fs_coverage', '=', 'all'), order='id')
        return contracts.filtered(lambda c: c._fs_covers())[:1].with_env(self.env)

    def _fs_apply_contract_coverage(self):
        self.ensure_one()
        contract = self.sudo().fs_subscription_id
        if contract and not self.is_covered and contract._fs_covers(job_only=True):
            self.write({'is_covered': True, 'coverage': 'contract'})

    def _fs_mobile_data(self):
        data = super()._fs_mobile_data()
        data['extra']['contract'] = self.sudo().fs_subscription_id.name or ''
        return data
