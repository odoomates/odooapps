from markupsafe import Markup

from odoo import models


class FollowupPrint(models.TransientModel):
    _inherit = 'followup.print'

    def process_partners(self, partner_ids, data):
        """ The levels that send a WhatsApp send it, in the batch and in the
        daily automatic follow-ups. """
        result = super().process_partners(partner_ids, data)
        stats = self.env['followup.stat.by.partner'].browse(partner_ids).filtered('max_followup_id.send_whatsapp')
        sent = self.env['res.partner']
        for stat in stats:
            sent |= stat.partner_id._om_whatsapp_followup_send(stat.max_followup_id)
        if stats:
            result['resulttext'] += Markup("<p>%s</p>") % self.env._(
                "%(sent)s WhatsApp message(s) sent of %(total)s", sent=len(sent), total=len(stats))
        return result
