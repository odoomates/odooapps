from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_ticket_count = fields.Integer(
        compute='_compute_om_ticket_count', string='Helpdesk Tickets', groups='om_helpdesk.group_helpdesk_user')

    def _compute_om_ticket_count(self):
        commercial = self.commercial_partner_id
        data = dict(self.env['om.helpdesk.ticket'].with_context(active_test=False)._read_group(
            [('commercial_partner_id', 'in', commercial.ids)], ['commercial_partner_id'], ['__count']))
        for partner in self:
            partner.om_ticket_count = data.get(partner.commercial_partner_id, 0)

    def action_view_om_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_ticket')
        action['domain'] = [('commercial_partner_id', '=', self.commercial_partner_id.id)]
        action['context'] = {'default_partner_id': self.id}
        action['display_name'] = self.env._('Tickets of %s', self.commercial_partner_id.display_name)
        return action
