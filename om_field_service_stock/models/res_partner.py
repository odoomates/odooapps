from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fs_equipment_ids = fields.One2many('om.fs.equipment', 'partner_id', string="Equipment at Site")
    fs_equipment_count = fields.Integer(compute='_compute_fs_equipment_count', string="Equipment Count",
                                        groups='om_field_service.group_fs_user')

    def _compute_fs_equipment_count(self):
        Equipment = self.env['om.fs.equipment']
        for partner in self:
            partner.fs_equipment_count = Equipment.search_count(
                [('commercial_partner_id', '=', partner.commercial_partner_id.id)]) if partner.id else 0

    def action_view_fs_equipment(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service_stock.action_om_fs_equipment')
        action['domain'] = [('commercial_partner_id', '=', self.commercial_partner_id.id)]
        action['context'] = {'default_partner_id': self.id}
        return action
