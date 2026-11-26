from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_quality_alert_on_failure = fields.Boolean(related='company_id.om_quality_alert_on_failure', readonly=False)
    module_om_quality_stock = fields.Boolean(string='Inventory Checks')
    module_om_quality_mrp = fields.Boolean(string='Manufacturing Checks')
