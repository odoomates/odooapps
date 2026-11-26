from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    om_quality_quarantine_location_id = fields.Many2one(
        'stock.location', string='Quarantine Location', check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        help="Where a failed quality check sends the goods. Created at the first quarantine when empty. "
             "Keep it outside the stock location, so that deliveries do not reserve from it.")

    def _om_quality_quarantine_location(self):
        self.ensure_one()
        location = self.om_quality_quarantine_location_id
        if not location:
            location = self.env['stock.location'].sudo().create({
                'name': self.env._('Quarantine'),
                'usage': 'internal',
                'location_id': self.view_location_id.id,
                'company_id': self.company_id.id,
                'om_quality_quarantine': True,
            })
            self.sudo().om_quality_quarantine_location_id = location
        elif not location.om_quality_quarantine:
            location.sudo().om_quality_quarantine = True
        return location

    def write(self, vals):
        res = super().write(vals)
        if vals.get('om_quality_quarantine_location_id'):
            self.om_quality_quarantine_location_id.sudo().write({'om_quality_quarantine': True})
        return res
