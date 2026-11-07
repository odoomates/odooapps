from odoo import api, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        if read_records:
            # the restrictions of every cashier who may open this shop, users and employees alike
            read_records[0]['_om_pos_restrictions'] = self.env['om.pos.access']._om_pos_restrictions(config)
        return read_records
