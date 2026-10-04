# Who carries a profile besides its users: the members of its Odoo groups, and
# the users given it for a while (a replacement, a leave).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    group_ids = fields.Many2many(
        'res.groups', 'om_access_profile_res_groups_rel', 'profile_id', 'group_id',
        string='Odoo Groups', tracking=True, copy=False,
        help="Every member of these groups carries the profile, the members of the groups "
             "implying them included: users joining a group get it, users leaving it lose it.")
    assignment_ids = fields.One2many(
        'om.access.profile.assignment', 'profile_id', string='Temporary Users',
        context={'active_test': False})

    @api.constrains('group_ids')
    def _check_group_ids(self):
        technical = self.sudo().search([]).group_id
        for profile in self:
            if profile.group_ids & technical:
                raise ValidationError(_(
                    "The group of an access profile cannot give another profile: "
                    "pick the profile's users instead."))

    def _om_direct_users(self):
        """ The users of the profile and the users it is assigned to today. """
        self.ensure_one()
        return self.user_ids | self.assignment_ids.filtered(lambda line: line.state == 'active').user_id

    def _om_members(self):
        """ Every user carrying the profile, however they got it. """
        self.ensure_one()
        return self._om_direct_users() | self.group_ids.all_user_ids

    @api.model
    def _om_profiles_of(self, user):
        """ The profiles ``user`` carries: their own, the ones assigned to them
        today and the ones of their groups. """
        Assignment = self.env['om.access.profile.assignment'].sudo()
        assigned = Assignment.search([('user_id', '=', user.id), ('state', '=', 'active')]).profile_id
        by_group = self.sudo().search([('group_ids', 'in', user.all_group_ids.ids)])
        return user.access_profile_ids.sudo() | assigned | by_group


class OmAccessProfileAssignment(models.Model):
    _name = 'om.access.profile.assignment'
    _description = 'Temporary Access Profile Assignment'
    _order = 'date_from desc, id desc'
    _clear_cache_name = 'default'

    profile_id = fields.Many2one('om.access.profile', string='Access Profile', required=True,
                                 ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True,
                              domain=[('share', '=', False)])
    date_from = fields.Date(string='From', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Until', help="Included. Left empty, the assignment does not end.")
    note = fields.Char(string='Reason')
    state = fields.Selection([('planned', 'Planned'), ('active', 'Running'), ('ended', 'Ended')],
                             default='planned', required=True, readonly=True)
    active = fields.Boolean(default=True)

    _check_dates = models.Constraint(
        'CHECK(date_to IS NULL OR date_to >= date_from)',
        "An assignment cannot end before it starts.")

    @api.depends('profile_id', 'user_id')
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.profile_id.name or ''}: {line.user_id.name or ''}"

    def _om_state_today(self):
        self.ensure_one()
        # the day as the user lives it
        today = fields.Date.context_today(self.with_context(tz=self.user_id.tz or 'UTC'))
        if today < self.date_from:
            return 'planned'
        if self.date_to and today > self.date_to:
            return 'ended'
        return 'active'

    def _om_refresh(self):
        """ Bring the state of the assignments to today; archive the ended ones. """
        changed = self.browse()
        for line in self:
            state = line._om_state_today()
            if state != line.state or (state == 'ended' and line.active):
                values = {'state': state}
                if state == 'ended':
                    values['active'] = False
                super(OmAccessProfileAssignment, line).write(values)
                changed |= line
        if changed:
            profiles = changed.profile_id
            profiles._sync_group()
            profiles._check_last_administrator()
        return changed

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._om_refresh()
        return lines

    def write(self, vals):
        profiles = self.profile_id
        result = super().write(vals)
        if {'date_from', 'date_to', 'user_id', 'profile_id', 'active'} & set(vals):
            self.filtered('active')._om_refresh()
            (profiles | self.profile_id)._sync_group()
            (profiles | self.profile_id)._check_last_administrator()
        return result

    def unlink(self):
        profiles = self.profile_id
        result = super().unlink()
        profiles.exists()._sync_group()
        return result

    @api.model
    def _cron_refresh(self):
        self.search([('state', '!=', 'ended')])._om_refresh()


class ResGroups(models.Model):
    _inherit = 'res.groups'

    def write(self, vals):
        result = super().write(vals)
        # a member added or removed from the group's side changes their profiles
        if {'user_ids', 'implied_ids', 'implied_by_ids'} & set(vals) \
                and self.env['om.access.profile'].sudo().search_count([('group_ids', '!=', False)], limit=1):
            self.env.transaction.invalidate_ormcache('default')
        return result
