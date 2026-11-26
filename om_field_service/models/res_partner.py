from urllib.parse import quote_plus

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fs_job_count = fields.Integer(compute='_compute_fs_job_count', string="Field Service Job Count",
                                  groups='om_field_service.group_fs_user')

    def _compute_fs_job_count(self):
        Task = self.env['project.task']
        for partner in self:
            partner.fs_job_count = Task.search_count([
                ('is_field_service', '=', True),
                ('partner_id', 'child_of', partner.commercial_partner_id.id),
            ]) if partner.id else 0

    def action_view_fs_jobs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_field_service.action_om_fs_job')
        action['domain'] = [('partner_id', 'child_of', self.commercial_partner_id.id)]
        action['context'] = {'default_partner_id': self.id}
        return action

    def _fs_map_urls(self):
        """ Navigation links to the address: geo URI, Google Maps, Apple Maps and OpenStreetMap. """
        self.ensure_one()
        if self.partner_latitude or self.partner_longitude:
            lat, lng = self.partner_latitude, self.partner_longitude
            point = f'{lat},{lng}'
            return {
                'geo': f'geo:{point}?q={point}',
                'google': f'https://www.google.com/maps/dir/?api=1&destination={point}',
                'apple': f'https://maps.apple.com/?daddr={point}',
                'osm': f'https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=17/{lat}/{lng}',
            }
        address = quote_plus(self._fs_address_line())
        if not address:
            return {}
        return {
            'geo': f'geo:0,0?q={address}',
            'google': f'https://www.google.com/maps/dir/?api=1&destination={address}',
            'apple': f'https://maps.apple.com/?daddr={address}',
            'osm': f'https://www.openstreetmap.org/search?query={address}',
        }

    def _fs_address_line(self):
        self.ensure_one()
        parts = [self.street, self.street2, ' '.join(filter(None, [self.zip, self.city])),
                 self.state_id.name, self.country_id.name]
        return ', '.join(part for part in parts if part)
