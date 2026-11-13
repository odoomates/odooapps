from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_reconcile_auto = fields.Boolean(related='company_id.om_reconcile_auto', readonly=False)
