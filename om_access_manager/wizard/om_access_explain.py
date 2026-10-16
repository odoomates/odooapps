# Why can, or can't, a user do something? The answer of Odoo itself (the groups
# and their access rules), then of the access profiles, on the model or on one
# record, with what else the profiles restrict there and the recent refusals.
from markupsafe import Markup, escape

from odoo import _, api, fields, models

from odoo.addons.base.models.ir_access import IN_SELECTION

from ..models.om_access_profile import BLOCK_MODES, OPERATIONS

YES = Markup('<span class="text-success fw-bold">&#10003;</span>')
NO = Markup('<span class="text-danger fw-bold">&#10007;</span>')
SOME = Markup('<span class="text-warning fw-bold">&#9681;</span>')

# the methods of a refusal, and the operation they need
READ_METHODS = frozenset({'read', 'search', 'search_read', 'web_read', 'web_search_read', 'search_count',
                          'read_group', 'web_read_group', 'formatted_read_group', 'export_data', 'name_search'})


class OmAccessExplain(models.TransientModel):
    _name = 'om.access.explain'
    _description = 'Explain the Access of a User'

    user_id = fields.Many2one('res.users', string='User', required=True, domain=[('share', '=', False)])
    model_id = fields.Many2one('ir.model', string='Data', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    operation = fields.Selection([
        ('read', 'Read'), ('write', 'Edit'), ('create', 'Create'), ('unlink', 'Delete'),
    ], required=True, default='read')
    res_id = fields.Integer(string='Record ID', help="Optional: the record to check, by its id.")
    record_name = fields.Char(string='Record', compute='_compute_record_name')
    verdict = fields.Selection([
        ('allowed', 'Allowed'), ('some', 'Allowed on Some Records'), ('denied', 'Denied'),
    ], compute='_compute_report')
    report = fields.Html(compute='_compute_report', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        if context.get('active_model') == 'res.users' and context.get('active_id'):
            values.setdefault('user_id', context['active_id'])
        if context.get('active_model') == 'om.user.audit.log' and context.get('active_id'):
            values.update(self._values_of_refusal(self.env['om.user.audit.log'].browse(context['active_id'])))
        return values

    @api.model
    def _values_of_refusal(self, line):
        """ The question a refusal of the audit log raises. """
        line = line.sudo()
        values = {'user_id': line.user_id.id}
        if line.model and line.model in self.env:
            values['model_id'] = self.env['ir.model']._get(line.model).id
            values['res_id'] = line.res_id or 0
            method = line.method or ''
            values['operation'] = (
                method if method in OPERATIONS
                else 'read' if method in READ_METHODS
                else 'write'
            )
        return values

    @api.depends('model_id', 'res_id')
    def _compute_record_name(self):
        for wizard in self:
            record = wizard._record()
            wizard.record_name = record.display_name if record else False

    def _record(self):
        """ The record to check, read as the superuser, or an empty recordset. """
        self.ensure_one()
        if not self.model_id or not self.res_id or self.model_id.model not in self.env:
            return None
        record = self.env[self.model_id.model].sudo().with_context(active_test=False).browse(self.res_id)
        return record.exists() or None

    def _user_env(self):
        """ The environment of the user, in all their companies, as at sign-in. """
        user = self.user_id.sudo()
        return self.env(user=user.id, su=False, context=dict(
            self.env.context, allowed_company_ids=user.company_ids.ids, lang=self.env.lang))

    @api.depends('user_id', 'model_id', 'operation', 'res_id')
    def _compute_report(self):
        for wizard in self:
            if not (wizard.user_id and wizard.model_id and wizard.operation) \
                    or wizard.model_id.model not in self.env:
                wizard.verdict = False
                wizard.report = False
                continue
            wizard.verdict, wizard.report = wizard._explain()

    #
    # the answer
    #

    def _explain(self):
        self.ensure_one()
        model_name = self.model_id.model
        operation = self.operation
        env = self._user_env()
        record = self._record() if operation != 'create' else None
        Model = env[model_name]

        final = Model._access_domain(operation)
        if record:
            verdict = 'allowed' if record.with_env(env).has_access(operation) else 'denied'
        elif final.is_false():
            verdict = 'denied'
        else:
            verdict = 'allowed' if final.is_true() else 'some'

        parts = [
            self._render_verdict(verdict, record),
            self._render_odoo(env, model_name, operation, record),
            self._render_profiles(env, model_name, operation, record),
        ]
        rules = self.env['om.access.profile']._resolve(self.user_id.id)
        if rules.enabled:
            parts.append(self._render_more(rules, model_name))
        parts.append(self._render_refusals(model_name))
        return verdict, Markup('').join(part for part in parts if part)

    def _operation_label(self):
        return dict(self._fields['operation']._description_selection(self.env))[self.operation]

    def _render_verdict(self, verdict, record):
        what = self.model_id.name
        if record:
            what = _("%(model)s \"%(record)s\"", model=what, record=record.display_name)
        sentences = {
            'allowed': _("%(user)s can %(operation)s %(what)s.",
                         user=self.user_id.name, operation=self._operation_label().lower(), what=what),
            'some': _("%(user)s can %(operation)s some %(what)s records only.",
                      user=self.user_id.name, operation=self._operation_label().lower(), what=what),
            'denied': _("%(user)s cannot %(operation)s %(what)s.",
                        user=self.user_id.name, operation=self._operation_label().lower(), what=what),
        }
        css = {'allowed': 'success', 'some': 'warning', 'denied': 'danger'}[verdict]
        return Markup('<div class="alert alert-%s mb-3" role="status"><b>%s</b></div>') % (css, sentences[verdict])

    def _render_odoo(self, env, model_name, operation, record):
        """ What Odoo itself grants: the access rules of the user's groups (one
        is enough), and the rules of no group (all must pass). """
        IrAccess = env['ir.access']
        accesses = [access for access in IrAccess.sudo()._get_all_access().get(model_name, ())
                    if access.operation in IN_SELECTION[operation]]
        group_ids = set(self.user_id.sudo()._get_group_ids())
        grants = [access for access in accesses if access.group_id and access.group_id in group_ids]
        restrictions = [access for access in accesses if not access.group_id]
        records = self.env['ir.access'].sudo().browse([access.id for access in grants + restrictions])
        by_id = {access.id: access for access in records}

        failing = set()
        if record:
            failing = set(IrAccess.with_env(env)._get_failed_accesses(record.with_env(env), operation).ids)

        rows = []
        for access in grants:
            line = by_id[access.id]
            mark = NO if access.id in failing else YES
            rows.append(Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>') % (
                mark, _("Grants"), Markup('%s<br/><small class="text-muted">%s</small>') % (
                    line.name, line.group_id.full_name), line.domain or '-'))
        for access in restrictions:
            line = by_id[access.id]
            mark = NO if access.id in failing else YES
            rows.append(Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>') % (
                mark, _("Limits everyone"), line.name, line.domain or '-'))

        title = Markup('<h4>%s</h4>') % _("1. Odoo's own access")
        if not grants:
            groups = self.env['ir.access'].sudo()._get_groups_with_access(model_name, operation)
            hint = ', '.join(groups[:5].mapped('full_name'))
            text = _("None of the groups of the user gives this right, whatever the profiles say.")
            if hint:
                text += ' ' + _("Groups that would: %s.", hint)
            return title + Markup('<p>%s %s</p>') % (NO, text)
        intro = Markup('<p class="text-muted">%s</p>') % _(
            "One rule of the user's groups is enough; the rules of no group apply to everyone.")
        table = Markup(
            '<table class="table table-sm"><tr><th></th><th>%s</th><th>%s</th><th>%s</th></tr>%s</table>'
        ) % (_("Effect"), _("Rule"), _("Records"), Markup('').join(rows))
        return title + intro + table

    def _render_profiles(self, env, model_name, operation, record):
        Profile = self.env['om.access.profile'].sudo()
        title = Markup('<h4>%s</h4>') % _("2. Access profiles")
        user = self.user_id.sudo()
        if user.id in Profile._exempt_user_ids():
            return title + Markup('<p>%s</p>') % _(
                "This user is the administrator of the database: profiles never restrict them.")
        rules = Profile._resolve(user.id)
        applied = Profile.browse([profile.id for profile in rules.additive + rules.override])
        skipped = Profile.with_context(active_test=False)._om_profiles_of(user) - applied
        notes = [self._render_skipped(profile, user) for profile in skipped]
        if not rules.enabled:
            text = Markup('<p>%s %s</p>') % (YES, _("No profile applies to this user: nothing is taken away."))
            return title + text + Markup('').join(notes)

        rows = []
        for kind, profiles in ((_("Additive"), rules.additive), (_("Override"), rules.override)):
            for profile in profiles:
                allows = profile.allows(model_name, operation)
                if not allows and operation != 'read' and 'global_readonly' in profile.flags:
                    why = _("Read only everywhere")
                elif model_name in profile.sources:
                    why = _("From the menus %s", ' / '.join(profile.sources[model_name]))
                elif model_name in profile.perms:
                    why = _("From its rule on this data")
                else:
                    why = _("Says nothing about this data")
                terms = profile.domain_terms(model_name, operation)
                rows.append(Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>') % (
                    YES if allows else NO, profile.name, kind, why, ' AND '.join(terms) or '-'))
        table = Markup(
            '<table class="table table-sm"><tr><th></th><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>%s</table>'
        ) % (_("Profile"), _("Combines as"), _("Why"), _("Record filter"), Markup('').join(rows))
        intro = Markup('<p class="text-muted">%s</p>') % _(
            "Additive profiles allow what one of them allows; an override profile takes away "
            "whatever the others allow.")

        verdict = []
        if not rules.allows(model_name, operation):
            verdict.append(Markup('<p>%s %s</p>') % (NO, _("Together, the profiles refuse this operation.")))
        else:
            restricted = env[model_name]._om_profile_domain(rules, operation)
            if restricted is None:
                verdict.append(Markup('<p>%s %s</p>') % (YES, _("Together, the profiles allow it on every record.")))
            elif record:
                inside = bool(record.filtered_domain(restricted))
                verdict.append(Markup('<p>%s %s</p>') % (
                    (YES, _("The record is among the ones the profiles leave to the user.")) if inside else
                    (NO, _("The record is outside the ones the profiles leave to the user."))))
            else:
                verdict.append(Markup('<p>%s %s</p>') % (SOME, _("Together, the profiles allow it on some records only.")))
        return title + intro + table + Markup('').join(verdict) + Markup('').join(notes)

    def _render_skipped(self, profile, user):
        if not profile.active:
            reason = _("archived")
        elif profile.company_id and profile.company_id not in user.company_ids:
            reason = _("for a company the user is not in")
        elif not profile.apply_to_admin and user._has_group('base.group_system'):
            reason = _("not applied to administrators")
        else:
            reason = _("not applied")
        return Markup('<p class="text-muted">%s</p>') % _(
            "The profile %(profile)s does not apply: %(reason)s.", profile=profile.name, reason=reason)

    def _render_more(self, rules, model_name):
        """ What else the profiles restrict on this data: fields and buttons. """
        profiles = rules.additive + rules.override
        names = sorted({field for profile in profiles
                        for model, field in (*profile.field_modes, *profile.field_conditions) if model == model_name})
        Model = self.env[model_name]
        labels = {'hide': _("Hidden"), 'readonly': _("Read only"), 'required': _("Required")}
        modes = [(mode, labels[mode]) for mode in ('hide', 'readonly', 'required')]
        lines, seen = [], set()
        for mode, label in modes:
            always, sometimes = [], []
            for name in names:
                if name in seen:
                    continue  # listed under its strongest mode
                condition = rules.field_condition(model_name, name, mode)
                if condition is None:
                    continue
                seen.add(name)
                field = Model._fields.get(name)
                text = field._description_string(self.env) if field is not None else name
                (always if condition is True else sometimes).append(text)
            if always:
                lines.append('%s: %s' % (label, ', '.join(always)))
            if sometimes:
                lines.append(_("%(mode)s under a condition: %(fields)s", mode=label, fields=', '.join(sometimes)))
        buttons = sorted({
            rule[3] for profile in profiles for rule in profile.buttons
            if rule[0] == model_name and rules.button_condition(BLOCK_MODES, model_name, rule[2], rule[3]) is not None
        })
        if buttons:
            lines.append(_("Buttons blocked: %s", ', '.join(buttons)))
        if not lines:
            return None
        return Markup('<h4>%s</h4><ul>%s</ul>') % (
            _("3. Also restricted on this data"),
            Markup('').join(Markup('<li>%s</li>') % line for line in lines))

    def _render_refusals(self, model_name):
        Log = self.env['om.user.audit.log'].sudo()
        domain = [('user_id', '=', self.user_id.id), ('event', '=', 'refused')]
        logs = Log.search(domain + [('model', '=', model_name)], limit=8) or Log.search(domain, limit=8)
        if not logs:
            return None
        rows = Markup('').join(
            Markup('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
                fields.Datetime.to_string(fields.Datetime.context_timestamp(self, log.date)),
                log.model_name or log.model or '', log.res_name or '',
                escape((log.detail or '').split('\n')[0]))
            for log in logs)
        return Markup(
            '<h4>%s</h4><table class="table table-sm"><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>%s</table>'
        ) % (_("Recent refusals of this user"), _("Date"), _("Data"), _("Record"), _("Message"), rows)

    def action_preview(self):
        """ Open Odoo as the user, to see it. """
        self.ensure_one()
        return self.user_id.action_om_preview()
