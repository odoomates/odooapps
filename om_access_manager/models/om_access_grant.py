# Odoo 16 copies the groups a group implies onto its users, and never takes
# them back: a group granted by a profile would stay after the user leaves it.
# This ledger remembers which groups a profile added to which users (not the
# ones they had already), so that they go with the profile.
from odoo import fields, models


class OmAccessGrant(models.Model):
    _name = 'om.access.grant'
    _description = 'Group Added by an Access Profile'

    profile_id = fields.Many2one('om.access.profile', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    group_id = fields.Many2one('res.groups', required=True, ondelete='cascade')

    _sql_constraints = [
        ('unique_grant', 'UNIQUE(profile_id, user_id, group_id)', 'A profile adds a group to a user once.'),
    ]


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    def _om_granted_closure(self):
        """ The groups the profile grants, with the ones they imply. """
        self.ensure_one()
        if not self.active:
            return self.env['res.groups']
        granted = self.sudo().granted_group_ids
        return granted | granted.trans_implied_ids

    def _om_record_grants(self):
        """ Before the group of the profile is written: note the groups it is
        about to add to users who lack them. """
        Grant = self.env['om.access.grant'].sudo()
        for profile in self:
            wanted = profile._om_granted_closure()
            if not wanted:
                continue
            known = {(grant.user_id.id, grant.group_id.id) for grant in Grant.search([('profile_id', '=', profile.id)])}
            Grant.create([
                {'profile_id': profile.id, 'user_id': user.id, 'group_id': group.id}
                for user in profile.sudo()._om_direct_users()
                for group in wanted - user.groups_id
                if (user.id, group.id) not in known
            ])

    def _om_revoke_grants(self, everything=False):
        """ Take back the groups a profile added and no longer grants, unless
        another profile still grants them to the same user. """
        Grant = self.env['om.access.grant'].sudo()
        stale = Grant
        for profile in self:
            grants = Grant.search([('profile_id', '=', profile.id)])
            if everything:
                stale |= grants
                continue
            users = profile.sudo()._om_direct_users()
            wanted = profile._om_granted_closure()
            stale |= grants.filtered(lambda grant: grant.user_id not in users or grant.group_id not in wanted)
        pairs = {(grant.user_id, grant.group_id) for grant in stale}
        stale.unlink()
        for user, group in pairs:
            if not Grant.search_count([('user_id', '=', user.id), ('group_id', '=', group.id)], limit=1):
                user.sudo().write({'groups_id': [(3, group.id)]})
