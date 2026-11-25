from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    shiprocket_order_id = fields.Char(string='Shiprocket Order', copy=False, readonly=True)
    shiprocket_shipment_id = fields.Char(string='Shiprocket Shipment', copy=False, readonly=True)
    shiprocket_courier_name = fields.Char(string='Shiprocket Courier', copy=False, readonly=True)
    shiprocket_send_count = fields.Integer(copy=False, readonly=True)

    def action_shiprocket_tracking_status(self):
        for picking in self:
            if picking.delivery_type != 'shiprocket' or not picking.carrier_tracking_ref:
                continue
            lines = []
            for awb in [ref.strip() for ref in picking.carrier_tracking_ref.split(',') if ref.strip()]:
                data = picking.carrier_id._shiprocket_track(awb)
                if not data.get('track_status'):
                    lines.append(self.env._('%(awb)s: %(status)s', awb=awb,
                                            status=data.get('error') or self.env._('no tracking events yet')))
                    continue
                shipment = (data.get('shipment_track') or [{}])[0]
                activities = data.get('shipment_track_activities') or []
                status = shipment.get('current_status') or ''
                if activities:
                    last = activities[0]
                    status = '%s (%s, %s)' % (status or last.get('activity'), last.get('location') or '', last.get('date') or '')
                if data.get('etd'):
                    status = self.env._('%(status)s, expected %(etd)s', status=status, etd=data['etd'])
                lines.append('%s: %s' % (awb, status))
            if not lines:
                raise UserError(self.env._('There is no Shiprocket shipment to track.'))
            body = Markup('<br/>').join([self.env._('Shiprocket tracking status:')] + lines)
            picking.message_post(body=body)
        return True
