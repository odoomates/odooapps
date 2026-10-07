# Restrict an App: the menus, data, reports and actions of an app on one
# screen, written back as ordinary lines of the profile.
from odoo import api, fields, models
from odoo.fields import Command

from ..models.om_access_profile_model import OWNER_FIELDS, own_domain
from .om_access_load_models import ACTION_MODEL_FIELD

LEVELS = [
    ('current', 'As configured now'),
    ('full', 'Full access'),
    ('user', 'User, without configuration'),
    ('readonly', 'Read only'),
    ('none', 'No access'),
]
SCOPES = [
    ('all', 'All records'),
    ('own', 'Their own records'),
    ('custom', 'Custom filter'),
]
# An app of these modules owns nothing: every model of the framework would
# otherwise count as its own, and "No access" on Settings would lock everyone out.
FRAMEWORK_MODULES = frozenset({'base', 'web'})
INDENT = '\u2003'
# the two kinds of Action menu entries, and the profile field hiding each
ACTION_TYPES = {
    'ir.actions.server': 'hidden_action_ids',
    'ir.actions.act_window': 'hidden_window_action_ids',
}
PERMS = ('perm_read', 'perm_create', 'perm_write', 'perm_unlink')
LEVEL_PERMS = {
    'full': (True, True, True, True),
    'user': (True, True, True, False),
    'readonly': (True, False, False, False),
    'none': (False, False, False, False),
}


class OmAccessAppWizard(models.TransientModel):
    _name = 'om.access.app.wizard'
    _description = 'Restrict an App'

    profile_id = fields.Many2one(
        'om.access.profile', string='Profile', required=True, ondelete='cascade')
    app_id = fields.Many2one(
        'ir.ui.menu', string='App', domain=[('parent_id', '=', False)],
        help="The apps are the menus of the home screen.")
    level = fields.Selection(
        LEVELS, string='Access Level', default='current', required=True,
        help="Fills the checkboxes below, which you can then adjust one by "
             "one. Data shared with other apps is never changed by a level.")
    own_records = fields.Boolean(
        string='Only Their Own Records',
        help="On the data of this app that has a salesperson or a responsible "
             "user, the users only reach the records assigned to them.")
    menu_line_ids = fields.One2many(
        'om.access.app.wizard.menu', 'wizard_id', string='Menus')
    model_line_ids = fields.One2many(
        'om.access.app.wizard.model', 'wizard_id', string='Data')
    report_line_ids = fields.One2many(
        'om.access.app.wizard.report', 'wizard_id', string='Reports')
    action_line_ids = fields.One2many(
        'om.access.app.wizard.action', 'wizard_id', string='Actions')
    other_additive = fields.Boolean(compute='_compute_other_additive')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'profile_id' in fields_list and self.env.context.get('active_model') == 'om.access.profile':
            values.setdefault('profile_id', self.env.context.get('active_id'))
        return values

    @api.depends('profile_id')
    def _compute_other_additive(self):
        for wizard in self:
            profile = wizard.profile_id
            wizard.other_additive = profile.strictness == 'additive' and any(
                other != profile and other.strictness == 'additive'
                for user in profile._om_members() for other in profile._om_profiles_of(user)
            )

    #
    # what an app brings
    #

    def _app_menus(self):
        """ The menus of the app, depth first in their order on screen:
        [(menu, depth, is_config)]. """
        result = []
        app = self.app_id.sudo().with_context(**{'ir.ui.menu.full_list': True})
        xmlids = app.search([('id', 'child_of', app.id)]).get_external_id()

        def is_config_root(menu):
            name = xmlids.get(menu.id, '').split('.')[-1].lower()
            return 'config' in name or (menu.name or '').strip().lower() == 'configuration'

        def walk(menu, depth, config):
            config = config or (depth == 1 and is_config_root(menu))
            result.append((menu, depth, config))
            for child in menu.child_id.sorted(lambda m: (m.sequence, m.id)):
                walk(child, depth + 1, config)

        walk(app, 0, False)
        return result

    @api.model
    def _menu_model(self, menu):
        action = menu.sudo().action
        field_name = action and ACTION_MODEL_FIELD.get(action._name)
        model_name = field_name and action[field_name]
        return model_name if model_name and model_name in self.env else None

    @api.model
    def _line_models(self, model_name):
        """ The models holding the lines of a document, e.g. the order lines of
        an order: a one2many whose inverse deletes the lines with it. """
        model = self.env[model_name]
        found = []
        for field in model._fields.values():
            if field.type != 'one2many' or field.comodel_name == model_name:
                continue
            comodel = self.env[field.comodel_name]
            inverse = comodel._fields.get(field.inverse_name)
            if (inverse is not None and inverse.type == 'many2one'
                    and inverse.ondelete == 'cascade'
                    and not comodel._transient and not comodel._abstract and comodel._auto
                    and field.comodel_name not in found):
                found.append(field.comodel_name)
        return found

    def _app_modules(self):
        """ The module of the app and every installed module built on it. """
        xmlid = self.app_id.sudo().get_external_id().get(self.app_id.id, '')
        root = xmlid.split('.')[0] if xmlid else None
        if not root or root in FRAMEWORK_MODULES:
            return set()
        installed = self.env['ir.module.module'].sudo().search([('state', '=', 'installed')])
        dependencies = {
            module.name: set(module.dependencies_id.mapped('name')) for module in installed
        }
        owned = {root}
        grown = True
        while grown:
            grown = False
            for name, depends in dependencies.items():
                if name not in owned and depends & owned:
                    owned.add(name)
                    grown = True
        return owned

    @api.model
    def _creating_modules(self, model_names):
        """ {model: the module that created it} """
        self.env.cr.execute("""
            SELECT DISTINCT ON (m.model) m.model, d.module
              FROM ir_model m
              JOIN ir_model_data d ON d.model = 'ir.model' AND d.res_id = m.id
             WHERE m.model = ANY(%s)
          ORDER BY m.model, d.id
        """, [list(model_names)])
        return dict(self.env.cr.fetchall())

    def _apps_by_model(self):
        """ {model: names of the apps whose menus open it} """
        apps = {}
        Menu = self.env['ir.ui.menu'].sudo().with_context(**{'ir.ui.menu.full_list': True})
        for menu in Menu.search([('action', '!=', False)]):
            model_name = self._menu_model(menu)
            if not model_name:
                continue
            root = Menu.browse(int(menu.parent_path.split('/')[0]))
            apps.setdefault(model_name, set()).add(root.name)
        return apps

    @api.model
    def _owner_field(self, model_name):
        model = self.env[model_name]
        for name in OWNER_FIELDS:
            field = model._fields.get(name)
            if field is not None and field.type == 'many2one' and field.comodel_name == 'res.users':
                return name
        return False

    #
    # the screen
    #

    @api.onchange('app_id')
    def _onchange_app_id(self):
        self._load_lines()
        if self.level != 'current':
            self._apply_level()

    @api.onchange('level')
    def _onchange_level(self):
        if self.level == 'current':
            self._load_lines()
        else:
            self._apply_level()

    @api.onchange('own_records')
    def _onchange_own_records(self):
        self._apply_own_records()

    def _load_lines(self):
        """ The lines of the app, ticked as the profile has them now. """
        self.menu_line_ids = [Command.clear()]
        self.model_line_ids = [Command.clear()]
        self.report_line_ids = [Command.clear()]
        self.action_line_ids = [Command.clear()]
        if not self.app_id or not self.profile_id:
            return
        profile = self.profile_id

        hidden_menus = set(profile.hidden_menu_ids.ids)
        menus = self._app_menus()
        menu_lines = []
        model_order, config_only = [], {}
        for menu, depth, config in menus:
            path = [int(menu_id) for menu_id in menu.parent_path.split('/') if menu_id]
            menu_lines.append(Command.create({
                'menu_id': menu.id,
                'label': INDENT * depth + menu.name,
                'is_config': config,
                'visible': not hidden_menus.intersection(path),
            }))
            model_name = self._menu_model(menu)
            # a wizard holds no data: rights on it protect nothing and can only break it
            if model_name and not self.env[model_name]._transient:
                if model_name not in config_only:
                    model_order.append(model_name)
                    config_only[model_name] = config
                else:
                    config_only[model_name] = config_only[model_name] and config
        self.menu_line_ids = menu_lines

        # the documents, each followed by its lines
        ordered = []
        parent_of = {}
        for model_name in model_order:
            if model_name not in ordered:
                ordered.append(model_name)
            for line_model in self._line_models(model_name):
                if line_model not in ordered:
                    ordered.append(line_model)
                    parent_of[line_model] = model_name
                    config_only[line_model] = config_only[model_name]

        app_modules = self._app_modules()
        creators = self._creating_modules(ordered)
        apps_by_model = self._apps_by_model()
        ir_models = {
            record.model: record
            for record in self.env['ir.model'].sudo().search([('model', 'in', ordered)])
        }
        rows = {line.model_id.model: line for line in profile.model_ids}
        model_lines = []
        for model_name in ordered:
            ir_model = ir_models.get(model_name)
            if not ir_model:
                continue
            parent = parent_of.get(model_name)
            owned = creators.get(model_name) in app_modules
            others = sorted(apps_by_model.get(model_name, set()) - {self.app_id.name})
            owner_field = self._owner_field(model_name)
            row = rows.get(model_name)
            domain = (row.domain or '').strip() if row else ''
            if not domain:
                scope = 'all'
            elif owner_field and domain == own_domain(owner_field):
                scope = 'own'
            else:
                scope = 'custom'
            values = {
                'model_id': ir_model.id,
                'label': (INDENT + ir_model.name) if parent else ir_model.name,
                'parent_label': ir_models[parent].name if parent in ir_models else False,
                'owned': owned,
                'is_config': config_only.get(model_name, False),
                'shared_with': ', '.join(others) if not owned and others else False,
                'owner_field': owner_field,
                'scope': scope,
                'custom_domain': domain if scope == 'custom' else False,
            }
            for perm in PERMS:
                values[perm] = row[perm] if row else True
            model_lines.append(Command.create(values))
        self.model_line_ids = model_lines

        model_names = [name for name in ordered if name in ir_models]
        hidden_reports = set(profile.hidden_report_ids.ids)
        reports = self.env['ir.actions.report'].sudo().search(
            [('model', 'in', model_names)], order='model, name')
        self.report_line_ids = [Command.create({
            'report_id': report.id,
            'model_label': ir_models[report.model].name,
            'visible': report.id not in hidden_reports,
        }) for report in reports]

        hidden_actions = set(profile.hidden_action_ids.ids + profile.hidden_window_action_ids.ids)
        action_lines = []
        for action_model in ACTION_TYPES:
            for action in self.env[action_model].sudo().search([
                ('binding_model_id.model', 'in', model_names),
                ('binding_type', '=', 'action'),
            ], order='name'):
                action_lines.append(Command.create({
                    'action_ref': f'{action_model},{action.id}',
                    'model_label': action.binding_model_id.name,
                    'visible': action.id not in hidden_actions,
                }))
        self.action_line_ids = action_lines

    def _apply_level(self):
        """ Tick the boxes the way the chosen level says. Shared data is left
        alone: its rights are those of every app using it. """
        level = self.level
        if level == 'current':
            return
        for line in self.menu_line_ids:
            line.visible = level == 'full' or (level != 'none' and not line.is_config)
        for line in self.model_line_ids.filtered('owned'):
            perms = LEVEL_PERMS[level]
            if level == 'user' and line.is_config:
                perms = LEVEL_PERMS['readonly']
            for perm, value in zip(PERMS, perms):
                line[perm] = value
        for line in self.report_line_ids:
            line.visible = level != 'none'
        for line in self.action_line_ids:
            line.visible = level in ('full', 'user')
        self._apply_own_records()

    def _apply_own_records(self):
        for line in self.model_line_ids.filtered(lambda line: line.owned and line.owner_field):
            if self.own_records and self.level != 'none':
                if line.scope == 'all':
                    line.scope = 'own'
            elif line.scope == 'own':
                line.scope = 'all'

    #
    # writing the profile
    #

    def action_apply(self):
        self.ensure_one()
        profile = self.profile_id

        # menus: only the topmost unticked menu is stored, it hides its children
        app_menus = self.menu_line_ids.menu_id
        unticked = set(self.menu_line_ids.filtered(lambda line: not line.visible).menu_id.ids)
        hidden = self.env['ir.ui.menu']
        for line in self.menu_line_ids.filtered(lambda line: not line.visible):
            ancestors = [int(menu_id) for menu_id in line.menu_id.parent_path.split('/') if menu_id][:-1]
            if not unticked.intersection(ancestors):
                hidden |= line.menu_id
        profile.hidden_menu_ids = (profile.hidden_menu_ids - app_menus) | hidden

        rows = {row.model_id.id: row for row in profile.model_ids}
        to_create = []
        for line in self.model_line_ids:
            if line.scope == 'own' and line.owner_field:
                domain = own_domain(line.owner_field)
            elif line.scope == 'custom':
                domain = line.custom_domain or False
            else:
                domain = False
            values = {perm: line[perm] for perm in PERMS}
            values['domain'] = domain
            neutral = all(values[perm] for perm in PERMS) and not domain
            row = rows.get(line.model_id.id)
            if row:
                if neutral and row._om_only_rights():
                    row.unlink()
                else:
                    row.write(values)
            elif not neutral:
                to_create.append(dict(values, profile_id=profile.id, model_id=line.model_id.id))
        if to_create:
            self.env['om.access.profile.model'].create(to_create)

        app_reports = self.report_line_ids.report_id
        hidden_reports = self.report_line_ids.filtered(lambda line: not line.visible).report_id
        profile.hidden_report_ids = (profile.hidden_report_ids - app_reports) | hidden_reports

        for action_model, field_name in ACTION_TYPES.items():
            lines = self.action_line_ids.filtered(
                lambda line: line.action_ref and line.action_ref._name == action_model)
            Action = self.env[action_model]
            app_actions = Action.browse([line.action_ref.id for line in lines])
            hidden_actions = Action.browse(
                [line.action_ref.id for line in lines if not line.visible])
            profile[field_name] = (profile[field_name] - app_actions) | hidden_actions
        return {'type': 'ir.actions.act_window_close'}


class OmAccessAppWizardMenu(models.TransientModel):
    _name = 'om.access.app.wizard.menu'
    _description = 'Restrict an App: Menu'

    wizard_id = fields.Many2one('om.access.app.wizard', required=True, ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', string='Menu Record', required=True, ondelete='cascade')
    label = fields.Char(string='Menu')
    is_config = fields.Boolean(string='Configuration')
    visible = fields.Boolean(string='Shown', default=True)


class OmAccessAppWizardModel(models.TransientModel):
    _name = 'om.access.app.wizard.model'
    _description = 'Restrict an App: Data'

    wizard_id = fields.Many2one('om.access.app.wizard', required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    label = fields.Char(string='Data')
    parent_label = fields.Char(string='Lines of')
    owned = fields.Boolean(string='Of this App')
    is_config = fields.Boolean(string='Configuration')
    shared_with = fields.Char(string='Also Used by')
    owner_field = fields.Char()
    perm_read = fields.Boolean(string='Read', default=True)
    perm_create = fields.Boolean(string='Create', default=True)
    perm_write = fields.Boolean(string='Edit', default=True)
    perm_unlink = fields.Boolean(string='Delete', default=True)
    scope = fields.Selection(SCOPES, string='Records', default='all', required=True)
    custom_domain = fields.Char(string='Filter')


class OmAccessAppWizardReport(models.TransientModel):
    _name = 'om.access.app.wizard.report'
    _description = 'Restrict an App: Report'

    wizard_id = fields.Many2one('om.access.app.wizard', required=True, ondelete='cascade')
    report_id = fields.Many2one('ir.actions.report', required=True, ondelete='cascade')
    model_label = fields.Char(string='Printed from')
    visible = fields.Boolean(string='Allowed', default=True)


class OmAccessAppWizardAction(models.TransientModel):
    _name = 'om.access.app.wizard.action'
    _description = 'Restrict an App: Action'

    wizard_id = fields.Many2one('om.access.app.wizard', required=True, ondelete='cascade')
    # a reference: server and window actions live in two tables
    action_ref = fields.Reference(
        [('ir.actions.server', 'Server Action'), ('ir.actions.act_window', 'Window Action')],
        string='Action', required=True)
    model_label = fields.Char(string='Action Menu of')
    visible = fields.Boolean(string='Allowed', default=True)
