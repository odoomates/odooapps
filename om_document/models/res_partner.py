from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_documents_count = fields.Integer(string='Files in Documents', compute='_compute_om_documents_count',
                                        groups='om_document.group_documents_user')

    def _compute_om_documents_count(self):
        counts = dict(self.env['om.documents.document']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count']))
        for partner in self:
            partner.om_documents_count = counts.get(partner, 0)

    def action_open_om_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_document.action_documents')
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id, 'searchpanel_default_folder_id': False}
        action['display_name'] = self.env._('Documents of %s', self.display_name)
        return action
