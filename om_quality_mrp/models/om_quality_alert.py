from odoo import fields, models


class OmQualityAlert(models.Model):
    _inherit = 'om.quality.alert'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', index='btree_not_null', check_company=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', index='btree_not_null')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Centre', index='btree_not_null', check_company=True)
