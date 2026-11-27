from odoo import _, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_om_whatsapp_send(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send WhatsApp"),
            'res_model': 'om.whatsapp.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_ids': self.ids, 'active_id': self.id},
        }
