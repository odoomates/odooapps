from odoo import api, fields, models


class OmFsJobPart(models.Model):
    _inherit = 'om.fs.job.part'

    is_billable = fields.Boolean(
        string="Billable", compute='_compute_is_billable', store=True, precompute=True, readonly=False,
        help="The part goes to the sales order of the job. Not billable by default on a covered job.")
    sale_line_id = fields.Many2one('sale.order.line', string="Sales Order Line", readonly=True, copy=False,
                                   index='btree_not_null')

    @api.depends('task_id.is_covered')
    def _compute_is_billable(self):
        for part in self:
            part.is_billable = not part.task_id.is_covered
