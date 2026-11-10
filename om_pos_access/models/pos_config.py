from odoo import models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _load_pos_data(self, data):
        result = super()._load_pos_data(data)
        if result['data']:
            # the restrictions of every cashier who may open this shop, users and employees alike
            config = self.browse(result['data'][0]['id'])
            result['data'][0]['_om_pos_restrictions'] = self.env['om.pos.access']._om_pos_restrictions(config)
        return result
