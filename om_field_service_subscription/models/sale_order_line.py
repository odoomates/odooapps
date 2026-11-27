from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    fs_maintenance = fields.Boolean(related='product_id.fs_maintenance', string="Maintenance Line")
    fs_next_job_date = fields.Date(
        string="Next Visit", copy=False,
        help="Date of the next maintenance visit: its job is created a few days before.")
