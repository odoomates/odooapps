from odoo import api, models


class ResPartner(models.Model):
    """ Contacts and addresses of the customers of a shop or a marketplace.

    The connectors give an address as a dict with the keys ``name``, ``company``, ``street``,
    ``street2``, ``city``, ``zip``, ``state_code``, ``country_code``, ``phone`` and ``email``
    (all optional), whatever the format of their own API. """
    _inherit = 'res.partner'

    @api.model
    def _connector_address_vals(self, address):
        """ The address fields of a contact for ``address``. """
        if not address:
            return {}
        country = self.env['res.country'].search([('code', '=ilike', address['country_code'])], limit=1) \
            if address.get('country_code') else self.env['res.country']
        state = self.env['res.country.state']
        if country and address.get('state_code'):
            state = state.search([('country_id', '=', country.id), ('code', '=ilike', address['state_code'])], limit=1)
        return {
            'street': address.get('street') or False,
            'street2': address.get('street2') or False,
            'city': address.get('city') or False,
            'zip': address.get('zip') or False,
            'country_id': country.id,
            'state_id': state.id,
        }

    @api.model
    def _connector_find_or_create(self, company, email, name, address=None, phone=None):
        """ The contact of a customer: the one with this email (a company or a person without a
        parent), else a new one with ``address``. """
        email = (email or '').strip()
        partner = self.browse()
        if email:
            partner = self.search([
                ('email', '=ilike', email), ('parent_id', '=', False),
                ('company_id', 'in', [False, company.id]),
            ], limit=1)
        if partner:
            return partner
        return self.create({
            'name': name or email or '?',
            'email': email or False,
            'phone': phone or (address or {}).get('phone') or False,
            **self._connector_address_vals(address),
        })

    def _connector_fill_blanks(self, vals):
        """ Fill the empty fields of this contact with ``vals``; never replace what is set. """
        self.ensure_one()
        self.write({key: value for key, value in vals.items() if value and not self[key]})

    def _connector_address(self, address_type, address):
        """ The ``address_type`` address (invoice, delivery) of this contact for ``address``:
        itself when it is the same, else one of its own addresses of this type, found or created.
        Never the address of another contact. """
        self.ensure_one()
        if not address:
            return self
        vals = self._connector_address_vals(address)
        name = address.get('name') or self.name

        def same(record):
            return all((record[key].id if hasattr(record[key], 'id') else record[key] or False) == value
                       for key, value in vals.items())

        if same(self) and name == self.name:
            return self
        child = self.child_ids.filtered(lambda c: c.type == address_type and c.name == name and same(c))[:1]
        if child:
            return child
        return self.create({
            'parent_id': self.id,
            'type': address_type,
            'name': name,
            'phone': address.get('phone') or False,
            **vals,
        })
