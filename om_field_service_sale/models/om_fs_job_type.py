from odoo import fields, models


class OmFsJobType(models.Model):
    _inherit = 'om.fs.job.type'

    service_product_id = fields.Many2one(
        'product.product', string="Service Product",
        domain="[('type', '=', 'service'), ('sale_ok', '=', True)]",
        help="Product of the sales order line that bills the time of the jobs of this type (hours from "
             "the timesheets). Empty: the default field service product.")
    bill_travel = fields.Boolean(
        string="Bill Travel Time", default=True,
        help="The travel time of the technicians is billed with the work time.")
