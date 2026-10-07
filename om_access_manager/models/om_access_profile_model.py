# Per model rules of a profile: R/C/U/D, record filters and model scoped UI switches.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

# the general filter first: it is ANDed with the per operation one
DOMAIN_FIELDS = ('domain', 'domain_read', 'domain_write', 'domain_create',
                 'domain_unlink')
# One-click record filters. They reach the user's data through a join, or through
# a field whose change clears the caches (res_users.py), so they do not go stale.
OWNER_FIELDS = ('user_id', 'invoice_user_id')
DRAFT_DOMAIN = "[('state', '=', 'draft')]"


def own_domain(field_name):
    # uid rather than user.id: the client's filter editor only knows uid
    return "[('%s', '=', uid)]" % field_name


DOMAIN_FIELD_OF_OPERATION = {
    'read': 'domain_read',
    'write': 'domain_write',
    'create': 'domain_create',
    'unlink': 'domain_unlink',
}


class OmAccessRightsMixin(models.AbstractModel):
    """ The four rights and the switches of some data: a model line sets them on
    one model, a menu line on the data of its whole branch. """
    _name = 'om.access.rights.mixin'
    _description = 'Access Rights and Switches'

    perm_read = fields.Boolean(string='Read', default=True)
    perm_write = fields.Boolean(string='Edit', default=True)
    perm_create = fields.Boolean(string='Create', default=True)
    perm_unlink = fields.Boolean(string='Delete', default=True)

    hide_chatter = fields.Boolean(string='Hide Chatter')
    hide_export = fields.Boolean(string='Block Export')
    hide_import = fields.Boolean(string='Block Import')
    hide_archive = fields.Boolean(string='Block Archiving')
    hide_duplicate = fields.Boolean(string='Block Duplication')
    hide_print = fields.Boolean(string='Hide Print Menu')
    hide_action_menu = fields.Boolean(string='Hide Action Menu')
    hide_send_message = fields.Boolean(string='Hide Send Message')
    hide_followers = fields.Boolean(string='Hide Followers')
    hide_attachments = fields.Boolean(string='Hide Attachments')


class OmAccessProfileModel(models.Model):
    _name = 'om.access.profile.model'
    _inherit = ['om.access.history.mixin', 'om.access.rights.mixin']
    _description = 'Access Profile Model Rule'
    _order = 'profile_id, model, id'

    _clear_cache_name = 'default'

    profile_id = fields.Many2one(
        'om.access.profile', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade')
    model = fields.Char(
        string='Technical Name', related='model_id.model', store=True, index=True)

    domain = fields.Char(
        string='Record Filter',
        help="Applies to all four operations. Only the records matching it are "
             "reachable. Evaluated with 'user', 'company_id' and 'company_ids', "
             "like a standard access domain.")
    domain_read = fields.Char(
        string='Read Filter',
        help="Narrows the records the user may read, on top of the general "
             "filter. Leave it empty to read everything the general filter allows.")
    domain_write = fields.Char(
        string='Edit Filter',
        help="Narrows the records the user may edit. This is how you say "
             "'may only edit draft records' without hiding the others.")
    domain_create = fields.Char(
        string='Create Filter',
        help="The records the user creates must match this filter.")
    domain_unlink = fields.Char(
        string='Delete Filter',
        help="Narrows the records the user may delete.")

    available_presets = fields.Char(compute='_compute_available_presets')

    _sql_constraints = [
        ('unique_model', 'UNIQUE(profile_id, model_id)',
         'A profile can only carry one rule per model.'),
    ]

    # a rule can take the access profiles away from the last administrator
    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.profile_id._check_last_administrator()
        return lines

    def write(self, vals):
        result = super().write(vals)
        self.profile_id._check_last_administrator()
        return result

    @api.constrains('domain', 'domain_read', 'domain_write', 'domain_create',
                    'domain_unlink', 'model_id')
    def _check_domain(self):
        eval_context = self.env['om.access.profile']._om_eval_context()
        for line in self:
            model = self.env[line.sudo().model_id.model].sudo()
            for field_name in DOMAIN_FIELDS:
                raw = (line[field_name] or '').strip()
                if not raw:
                    continue
                try:
                    expression.expression(safe_eval(raw, eval_context), model)
                except Exception as error:  # noqa: BLE001
                    raise ValidationError(_(
                        "Invalid %(filter)s on %(model)s: %(error)s",
                        filter=self._fields[field_name].string,
                        model=line.model_id.model, error=error)) from error

    @api.model
    def _preset_domains(self, model_name):
        """ {preset: (filter field, domain)} for the presets ``model_name`` can take. """
        if not model_name or model_name not in self.env:
            return {}
        model = self.env[model_name]

        def relation(name):
            field = model._fields.get(name)
            return field.comodel_name if field is not None and field.type == 'many2one' else None

        presets = {}
        owner = next((name for name in OWNER_FIELDS if relation(name) == 'res.users'), None)
        if owner:
            presets['own'] = ('domain', own_domain(owner))
        elif relation('employee_id') == 'hr.employee':
            presets['own'] = ('domain', "[('employee_id.user_id', '=', uid)]")
        if relation('team_id') == 'crm.team':
            presets['team'] = ('domain', "['|', ('team_id.user_id', '=', uid), "
                                         "('team_id.member_ids', 'in', [uid])]")
        if relation('company_id') == 'res.company':
            presets['company'] = ('domain', "['|', ('company_id', '=', False), "
                                            "('company_id', 'in', company_ids)]")
        if (relation('warehouse_id') == 'stock.warehouse'
                and 'property_warehouse_id' in self.env['res.users']._fields):
            presets['warehouse'] = ('domain', "[('warehouse_id', '=', user.property_warehouse_id.id)]")
        if 'hr.employee' in self.env:
            # theirs and those of the employees under them, three levels down,
            # through the org chart in SQL: never stale
            if owner:
                chain = [f"{owner}.employee_ids" + '.parent_id' * level + '.user_id' for level in range(1, 4)]
                presets['hierarchy'] = ('domain', "['|', '|', '|', ('%s', '=', uid), %s]" % (
                    owner, ', '.join("('%s', '=', uid)" % path for path in chain)))
            elif relation('employee_id') == 'hr.employee':
                chain = ['employee_id' + '.parent_id' * level + '.user_id' for level in range(4)]
                presets['hierarchy'] = ('domain', "['|', '|', '|', %s]" % ', '.join(
                    "('%s', '=', uid)" % path for path in chain))
        # dates from today: Odoo 15 has no relative dates in domains, the
        # access domains are computed again every day instead (base_model.py)
        if 'create_date' in model._fields:
            for key, start in (('today', 'context_today()'),
                               ('week', 'context_today() - relativedelta(days=context_today().weekday())'),
                               ('month', 'context_today().replace(day=1)'),
                               ('year', 'context_today().replace(month=1, day=1)')):
                presets[key] = ('domain', "[('create_date', '>=', (%s).strftime('%%Y-%%m-%%d'))]" % start)
        state = model._fields.get('state')
        if state is not None and state.type == 'selection' and 'draft' in dict(
                state._description_selection(self.env)):
            presets['draft'] = ('domain_write', DRAFT_DOMAIN)
        return presets

    @api.depends('model_id')
    def _compute_available_presets(self):
        for line in self:
            line.available_presets = ' '.join(self._preset_domains(line.model_id.model))

    def _apply_preset(self, preset):
        for line in self:
            field_name, domain = self._preset_domains(line.model_id.model)[preset]
            values = {field_name: domain}
            if preset == 'draft':
                # what may not be edited may not be deleted either
                values['domain_unlink'] = domain
            line.write(values)
        return self._reopen()

    def _reopen(self):
        # a dialog button returning nothing closes the dialog: reopen the rule
        return self.action_open_rule() if len(self) == 1 else None

    def action_preset_own(self):
        return self._apply_preset('own')

    def action_preset_team(self):
        return self._apply_preset('team')

    def action_preset_company(self):
        return self._apply_preset('company')

    def action_preset_warehouse(self):
        return self._apply_preset('warehouse')

    def action_preset_draft(self):
        return self._apply_preset('draft')

    def action_clear_filters(self):
        self.write(dict.fromkeys(DOMAIN_FIELDS, False))
        return self._reopen()

    def action_open_rule(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.model_id.name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('om_access_manager.om_access_profile_model_view_form').id, 'form')],
            'target': 'new',
        }

    def _om_history_kind(self):
        return _("data rule")

    def _om_history_label(self):
        rights = [label for name, label in (
            ('perm_read', _("Read")), ('perm_create', _("Create")),
            ('perm_write', _("Edit")), ('perm_unlink', _("Delete"))) if self[name]]
        label = '%s: %s' % (self.model_id.name or self.model, ', '.join(rights) or _("no access"))
        if any(self[name] for name in DOMAIN_FIELDS):
            label += ' + %s' % _("record filter")
        return label

    def _om_only_rights(self):
        """ True when the line holds nothing beyond the four rights and the general filter. """
        self.ensure_one()
        return not any(self[name] for name in DOMAIN_FIELDS[1:]) and not any(
            self[name] for name in ('hide_chatter', 'hide_export', 'hide_import',
                                    'hide_archive', 'hide_duplicate', 'hide_print',
                                    'hide_action_menu', 'hide_send_message', 'hide_followers',
                                    'hide_attachments'))

    def _set_perms(self, **values):
        return self.write(values)

    def action_set_readonly(self):
        return self._set_perms(perm_write=False, perm_create=False, perm_unlink=False)

    def action_set_full(self):
        return self._set_perms(
            perm_read=True, perm_write=True, perm_create=True, perm_unlink=True)
