import json

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    easypost_shipment_data = fields.Text(string='EasyPost Shipments', copy=False, readonly=True)

    def _easypost_shipments(self):
        self.ensure_one()
        try:
            records = json.loads(self.easypost_shipment_data or '[]')
        except ValueError:
            return []
        return records if isinstance(records, list) else []

    def action_easypost_tracking_status(self):
        for picking in self:
            records = [r for r in picking._easypost_shipments() if r.get('tracker_id')]
            if not records:
                raise UserError(self.env._('There is no EasyPost shipment to track.'))
            lines = []
            for record in records:
                tracker = picking.carrier_id._easypost_request('GET', '/trackers/%s' % record['tracker_id'])
                status = (tracker.get('status') or '').replace('_', ' ')
                details = tracker.get('tracking_details') or []
                if details:
                    last = details[-1]
                    location = last.get('tracking_location') or {}
                    place = ', '.join(part for part in (location.get('city'), location.get('state'),
                                                        location.get('country')) if part)
                    status = '%s: %s (%s %s)' % (status, last.get('message') or '', place, last.get('datetime') or '')
                if tracker.get('est_delivery_date'):
                    status = self.env._('%(status)s, expected %(date)s', status=status,
                                        date=tracker['est_delivery_date'][:10])
                lines.append('%s: %s' % (record.get('tracking_code'), status))
            body = Markup('<br/>').join([self.env._('EasyPost tracking status:')] + lines)
            picking.message_post(body=body)
        return True
