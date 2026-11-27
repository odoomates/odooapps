from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _om_ai_whatsapp_deliveries(self):
        """ The carrier of each delivery too, for the order status of the assistant. """
        result = super()._om_ai_whatsapp_deliveries()
        pickings = {picking.name: picking for picking in self.sudo().picking_ids}
        for item in result:
            picking = pickings.get(item['reference'])
            if picking and picking.carrier_id:
                item['carrier'] = picking.carrier_id.name
                links = picking._om_ai_whatsapp_tracking_links()
                if links:
                    item['tracking_url'] = ' '.join(links)
        return result
