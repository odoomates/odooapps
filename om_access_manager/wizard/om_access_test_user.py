# Shows the access a user really ends up with, all profiles combined, and
# which profile set each line.
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Labels are translated inside the methods, not at module level: a lazy string
# rendered by Markup loses the translation frame and logs a stack per row.
OPERATIONS = ('read', 'write', 'create', 'unlink')

YES = Markup('<span style="color:#28a745">&#10003;</span>')
NO = Markup('<span style="color:#dc3545">&#10007;</span>')


class OmAccessTestUser(models.TransientModel):
    _name = 'om.access.test.user'
    _description = 'Test the Effective Access of a User'

    user_id = fields.Many2one('res.users', string='User', required=True)
    # opened from a profile: only its members can be previewed
    profile_id = fields.Many2one('om.access.profile', string='Profile')
    preview_user_ids = fields.Many2many('res.users', compute='_compute_preview_user_ids')
    profile_ids = fields.Many2many(
        'om.access.profile', string='Profiles Applied', compute='_compute_result')
    report = fields.Html(string='Effective Access', compute='_compute_result', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'user_id' in fields_list and self.env.context.get('active_model') == 'res.users':
            values.setdefault('user_id', self.env.context.get('active_id'))
        return values

    @api.depends('profile_id')
    def _compute_preview_user_ids(self):
        for wizard in self:
            wizard.preview_user_ids = wizard.profile_id._om_preview_users() if wizard.profile_id else False

    def action_open_preview(self):
        self.ensure_one()
        if self.profile_id and self.user_id not in self.profile_id._om_preview_users():
            raise UserError(_("%(user)s does not have the profile %(profile)s: choose one of its users.",
                              user=self.user_id.name, profile=self.profile_id.name))
        return self.user_id.action_om_preview(back_url=self.env.context.get('om_preview_back'))

    @api.depends('user_id')
    def _compute_result(self):
        Profile = self.env['om.access.profile']
        for wizard in self:
            if not wizard.user_id:
                wizard.profile_ids = False
                wizard.report = False
                continue
            rules = Profile._resolve(wizard.user_id.id)
            wizard.profile_ids = Profile.browse(
                [profile.id for profile in rules.additive + rules.override])
            wizard.report = wizard._render_report(rules)

    def _render_report(self, rules):
        self.ensure_one()
        granted = self._render_granted()
        if not rules.enabled:
            return granted + Markup('<p>%s</p>') % _(
                "No access profile restricts this user: nothing is taken away.")

        parts = [granted, self._render_profiles(rules)]
        models_part = self._render_models(rules)
        if models_part:
            parts.append(models_part)
        parts.append(self._render_switches(rules))
        return Markup('').join(parts)

    @api.model
    def _operation_labels(self):
        return (
            ('read', _("Read")), ('write', _("Edit")),
            ('create', _("Create")), ('unlink', _("Delete")),
        )

    def _render_granted(self):
        """ The Odoo groups the user gets from their profiles. """
        profiles = self.env['om.access.profile'].sudo()._om_profiles_of(self.user_id.sudo()).filtered('active')
        rows = [
            Markup('<tr><td>%s</td><td>%s</td></tr>') % (group.full_name, profile.name)
            for profile in profiles for group in profile.granted_group_ids
        ]
        if not rows:
            return Markup('')
        return Markup(
            '<h4>%s</h4><table class="table table-sm"><tr><th>%s</th><th>%s</th></tr>%s</table>'
        ) % (_("Access granted"), _("Group"), _("By the profile"), Markup('').join(rows))

    def _render_profiles(self, rules):
        rows = []
        for label, profiles in ((_("Additive"), rules.additive),
                                (_("Override"), rules.override)):
            for profile in profiles:
                rows.append(Markup('<tr><td>%s</td><td>%s</td></tr>') % (
                    profile.name, label))
        return Markup(
            '<h4>%s</h4><table class="table table-sm"><tr><th>%s</th><th>%s</th></tr>%s</table>'
        ) % (_("Profiles applied"), _("Profile"), _("Combines as"), Markup('').join(rows))

    def _render_models(self, rules):
        # the models with rights, and those only filtered (by allowed records)
        names = sorted({
            model
            for profile in rules.additive + rules.override
            for model in (*profile.perms, *(model for model, _operation in profile.domains))
        })
        if not names:
            return None
        header = Markup('<tr><th>%s</th>%s<th>%s</th><th>%s</th></tr>') % (
            _("Model"),
            Markup('').join(
                Markup('<th>%s</th>') % label
                for _operation, label in self._operation_labels()
            ),
            _("Record filter"),
            _("Set by"),
        )
        rows = []
        for model_name in names:
            cells = Markup('').join(
                Markup('<td>%s</td>') % (YES if rules.allows(model_name, operation) else NO)
                for operation, _label in self._operation_labels()
            )
            domains = []
            for operation, label in self._operation_labels():
                or_groups, and_groups = rules.record_domains(model_name, operation)
                terms = [
                    ' AND '.join(group)
                    for group in list(or_groups or ()) + list(and_groups)
                ]
                if terms:
                    domains.append('%s: %s' % (label, ' OR '.join(terms)))
            authors = ', '.join(
                _("%(profile)s, from %(menus)s", profile=profile.name, menus=' / '.join(profile.sources[model_name]))
                if model_name in profile.sources else profile.name
                for profile in rules.additive + rules.override
                if model_name in profile.perms
                or any(model == model_name for model, _operation in profile.domains)
            )
            rows.append(Markup('<tr><td><code>%s</code></td>%s<td><code>%s</code></td><td>%s</td></tr>') % (
                model_name, cells, ' | '.join(domains) or '-', authors))
        return Markup('<h4>%s</h4><table class="table table-sm">%s%s</table>') % (
            _("Models"), header, Markup('').join(rows))

    def _render_switches(self, rules):
        labels = (
            ('global_readonly', _("Read only everywhere")),
            ('hide_chatter_all', _("Chatter hidden everywhere")),
            ('block_export', _("Export blocked")),
            ('block_archive', _("Archiving blocked")),
            ('block_duplicate', _("Duplication blocked")),
            ('hide_activities', _("Activities hidden")),
            ('hide_settings_menu', _("Settings app hidden")),
            ('lock_statusbar', _("Status bars locked")),
        )
        rows = Markup('').join(
            Markup('<tr><td>%s</td><td>%s</td></tr>') % (
                label, YES if rules.has_flag(flag) else NO)
            for flag, label in labels
        )
        hidden_menus = len(rules.menu_blacklist())
        rows += Markup('<tr><td>%s</td><td>%s</td></tr>') % (
            _("Hidden menu entries"), hidden_menus)
        return Markup('<h4>%s</h4><table class="table table-sm">%s</table>') % (
            _("Switches"), rows)
