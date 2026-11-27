from odoo import api, fields, models


class OmSocialIdentity(models.Model):
    """ A customer in a messaging channel: their address (a phone number, a
    handle), the user ID the channel gives them, their username and the name
    they gave themselves, and their contact once known. A contact has one
    identity per channel, which finds them when a message comes in. """
    _name = 'om.social.identity'
    _description = 'Social Identity'
    _order = 'channel, id'
    _rec_names_search = ['address', 'user_ref', 'username', 'profile_name', 'partner_id.name']

    channel = fields.Selection(selection='_selection_channel', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Contact', index='btree_not_null', ondelete='set null')
    address = fields.Char('Address', index='btree_not_null', help="Where the messages go: a phone number, a handle.")
    user_ref = fields.Char(
        'User ID', index='btree_not_null', copy=False,
        help="The id the channel gives this customer for your business: their messages reach this contact by it, "
             "and a message goes to it when their address is not known.")
    username = fields.Char('Username', copy=False, help="The username the customer chose in the channel.")
    profile_name = fields.Char('Profile Name', help="The name the customer gave themselves in the channel.")
    channel_ids = fields.One2many('discuss.channel', 'om_social_identity_id', string='Conversations')

    @api.model
    def _selection_channel(self):
        return self.env['om.social.account']._fields['channel'].selection

    @api.depends('channel', 'address', 'user_ref', 'username', 'profile_name')
    def _compute_display_name(self):
        labels = dict(self._fields['channel']._description_selection(self.env))
        for identity in self:
            name = (identity.username and f'@{identity.username}') or identity.address or identity.user_ref \
                or identity.profile_name or ''
            identity.display_name = f'{labels.get(identity.channel, "")}: {name}' if name else labels.get(
                identity.channel, "")

    def _om_social_label(self):
        """ How the customer is shown without a contact: the address, else the
        username, else the user ID. """
        self.ensure_one()
        return self.address or (self.username and f'@{self.username}') or self.user_ref or False

    @api.model
    def _om_social_search(self, channel, address=False, user_ref=False):
        """ The identities of ``channel`` with the user ID ``user_ref``, or
        with ``address``; those with a contact first. """
        if not (address or user_ref):
            return self.browse()
        domain = [('channel', '=', channel)]
        domain.append(('user_ref', '=', user_ref) if user_ref else ('address', '=', address))
        return self.sudo().search(domain, order='id').sorted(lambda identity: not identity.partner_id)

    @api.model
    def _om_social_get(self, channel, address=False, user_ref=False, username=False, profile_name=False,
                       partner=False):
        """ The identity of a customer of ``channel``, made or completed with
        what is known of them: by their user ID, else by their address when
        it has no other user ID. """
        identity = self._om_social_search(channel, user_ref=user_ref)[:1] if user_ref else self.browse()
        if not identity and address:
            identity = self._om_social_search(channel, address=address).filtered(
                lambda i: not user_ref or not i.user_ref)[:1]
        values = {key: value for key, value in (
            ('address', address), ('user_ref', user_ref), ('username', username), ('profile_name', profile_name),
            ('partner_id', partner.id if partner else False)) if value}
        if not identity:
            return self.sudo().create(dict(values, channel=channel))
        identity._om_social_learn(**values)
        return identity

    def _om_social_learn(self, address=False, user_ref=False, username=False, profile_name=False, partner_id=False):
        """ Complete the identity: a new username or profile name replaces
        the old one, an address or a contact is only set when missing. """
        self.ensure_one()
        values = {}
        if address and not self.address:
            values['address'] = address
        if user_ref and self.user_ref != user_ref:
            values['user_ref'] = user_ref
        if username and self.username != username:
            values['username'] = username
        if profile_name and self.profile_name != profile_name:
            values['profile_name'] = profile_name
        if partner_id and not self.partner_id:
            values['partner_id'] = partner_id
        if values:
            self.sudo().write(values)
