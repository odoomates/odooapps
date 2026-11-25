import re
from datetime import datetime, timezone

from markupsafe import Markup

from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_aramex_tracking_status(self):
        for picking in self:
            awbs = [ref.strip() for ref in (picking.carrier_tracking_ref or '').split(',') if ref.strip()]
            if picking.delivery_type != 'aramex' or not awbs:
                raise UserError(self.env._('There is no Aramex shipment to track.'))
            results = picking.carrier_id._aramex_track(awbs)
            lines = []
            for awb in awbs:
                updates = results.get(awb) or []
                if not updates:
                    lines.append(self.env._('%s: no tracking events yet', awb))
                    continue
                update = updates[0]
                lines.append('%s: %s (%s, %s)' % (
                    awb, update.get('UpdateDescription') or update.get('UpdateCode') or '',
                    update.get('UpdateLocation') or '', self._aramex_format_date(update.get('UpdateDateTime')),
                ))
            body = Markup('<br/>').join([self.env._('Aramex tracking status:')] + lines)
            picking.message_post(body=body)
        return True

    def _aramex_format_date(self, value):
        match = re.search(r'/Date\((-?\d+)', value or '')
        if not match:
            return value or ''
        return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
