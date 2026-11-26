from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_quality_lot_hold_reservation = fields.Boolean(
        related='company_id.om_quality_lot_hold_reservation', readonly=False)

    def action_om_quality_warehouses(self):
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_warehouse_form')
        action['context'] = {}
        return action
