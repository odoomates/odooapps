from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    fs_origin_task_id = fields.Many2one(
        'project.task', string="Follow-up of Job", index='btree_not_null', copy=False,
        help="Field service job this quotation was made from.")
    fs_job_ids = fields.One2many('project.task', 'fs_sale_order_id', string="Field Service Jobs")
    fs_job_count = fields.Integer(compute='_compute_fs_job_count', string="Job Count")

    @api.depends('fs_job_ids', 'fs_origin_task_id')
    def _compute_fs_job_count(self):
        for order in self:
            order.fs_job_count = len(order.fs_job_ids | order.fs_origin_task_id)

    def action_view_fs_jobs(self):
        self.ensure_one()
        jobs = self.fs_job_ids | self.fs_origin_task_id
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('id', 'in', jobs.ids)]
        action['context'] = {'om_fs_job': True}
        if len(jobs) == 1:
            action['views'] = [(self.env.ref('om_field_service.project_task_view_form_fs').id, 'form')]
            action['res_id'] = jobs.id
        return action


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    fs_part_ids = fields.One2many('om.fs.job.part', 'sale_line_id', string="Field Service Parts")

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        """ The parts used on a job already left the van of the technician: no delivery for them. """
        lines = self.filtered(lambda line: not line.fs_part_ids)
        return super(SaleOrderLine, lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)
