from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_3way_enabled = fields.Boolean(related='company_id.om_3way_enabled', readonly=False)
    om_3way_price_tol_percent = fields.Float(related='company_id.om_3way_price_tol_percent', readonly=False)
    om_3way_price_tol_amount = fields.Monetary(related='company_id.om_3way_price_tol_amount', readonly=False)
    om_3way_qty_tol_percent = fields.Float(related='company_id.om_3way_qty_tol_percent', readonly=False)
    om_3way_ordered_policy = fields.Selection(related='company_id.om_3way_ordered_policy', readonly=False)
    om_3way_no_po_policy = fields.Selection(related='company_id.om_3way_no_po_policy', readonly=False)
    om_3way_payment_policy = fields.Selection(related='company_id.om_3way_payment_policy', readonly=False)
    om_3way_activity = fields.Boolean(related='company_id.om_3way_activity', readonly=False)
