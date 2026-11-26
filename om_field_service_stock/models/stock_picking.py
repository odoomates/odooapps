from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    fs_task_id = fields.Many2one('project.task', string="Field Service Job", index='btree_not_null', copy=False)


class StockLocation(models.Model):
    _inherit = 'stock.location'

    fs_van_employee_ids = fields.One2many('hr.employee', 'van_location_id', string="Van of")
