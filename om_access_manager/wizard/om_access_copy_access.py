# Give a user the access of another: a replacement, a newcomer in the same job,
# or a job change when the access moves instead of being copied.
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmAccessCopyAccess(models.TransientModel):
    _name = 'om.access.copy.access'
    _description = 'Copy Access to Other Users'

    source_user_id = fields.Many2one('res.users', string='From', required=True,
                                     domain=[('share', '=', False)])
    user_ids = fields.Many2many('res.users', string='To', required=True, domain=[('share', '=', False)])
    mode = fields.Selection([
        ('copy', 'Copy: both keep it'),
        ('move', 'Move: take it away from the first user'),
    ], string='What to Do', default='copy', required=True)
    with_profiles = fields.Boolean(string='Access Profiles', default=True)
    with_assignments = fields.Boolean(string='Temporary Profiles', default=True,
                                      help="The running and planned ones, with their dates.")
    with_allowed = fields.Boolean(string='Allowed Records', default=True,
                                  help="This user's points of sale, warehouses, journals...")
    summary = fields.Html(compute='_compute_summary')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'source_user_id' in fields_list and self.env.context.get('active_model') == 'res.users':
            values.setdefault('source_user_id', self.env.context.get('active_id'))
        return values

    def _assignments(self):
        return self.env['om.access.profile.assignment'].sudo().search([
            ('user_id', '=', self.source_user_id.id), ('state', '!=', 'ended')])

    @api.depends('source_user_id', 'with_profiles', 'with_assignments', 'with_allowed')
    def _compute_summary(self):
        for wizard in self:
            source = wizard.source_user_id.sudo()
            items = []
            if wizard.with_profiles:
                items.append(_("Profiles: %s", ', '.join(source.access_profile_ids.mapped('name')) or _("none")))
            if wizard.with_assignments:
                items.append(_("Temporary profiles: %s", len(wizard._assignments()) if source else 0))
            if wizard.with_allowed:
                items.append(_("Allowed records: %s", len(source.access_allowed_ids)))
            wizard.summary = Markup('<ul>%s</ul>') % Markup('').join(
                Markup('<li>%s</li>') % item for item in items) if source else False

    def action_apply(self):
        self.ensure_one()
        source = self.source_user_id.sudo()
        targets = (self.user_ids - self.source_user_id).sudo()
        if not targets:
            raise UserError(_("Pick the users to give the access of %s to.", source.name))
        if self.with_profiles and source.access_profile_ids:
            targets.write({'access_profile_ids': [(4, profile.id) for profile in source.access_profile_ids]})
        if self.with_assignments:
            assignments = self._assignments()
            if assignments:
                self.env['om.access.profile.assignment'].sudo().create([{
                    'profile_id': line.profile_id.id, 'user_id': user.id, 'date_from': line.date_from,
                    'date_to': line.date_to, 'note': line.note,
                } for line in assignments for user in targets])
        if self.with_allowed:
            Allowed = self.env['om.access.allowed'].sudo()
            for user in targets:
                existing = {(line.kind, line.res_id) for line in user.access_allowed_ids}
                Allowed.create([
                    {'user_id': user.id, 'kind': line.kind, 'res_id': line.res_id}
                    for line in source.access_allowed_ids if (line.kind, line.res_id) not in existing
                ])
        if self.mode == 'move':
            if self.with_assignments:
                self._assignments().unlink()
            if self.with_allowed:
                source.access_allowed_ids.unlink()
            if self.with_profiles:
                source.write({'access_profile_ids': [(5,)]})
        return {'type': 'ir.actions.act_window_close'}
