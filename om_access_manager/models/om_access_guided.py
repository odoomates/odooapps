# Setup Wizard: a profile set up step by step in a pop-up (who, apps, each app,
# everywhere, review), for a new profile or an existing one. It keeps nothing of
# its own: every step writes the ordinary settings of the profile, through the
# same methods as the Configure screen, so both show the same profile.
import logging
import re

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

from .om_access_menu_panel import SIMPLE_FILTER_SKIPPED, _om_parse_simple_filter
from .om_access_profile import MODEL_FLAGS, PERM_FIELDS
from .om_access_profile_model import OWNER_FIELDS

# the switches of the Everywhere step, in its order
GUIDED_SWITCHES = (
    'block_export', 'block_import', 'block_archive', 'block_duplicate',
    'hide_costs', 'hide_sale_prices', 'block_developer_mode', 'global_readonly',
)
# the field a simple record filter starts on: what people limit this data by most
FILTER_BY_MODEL = {
    'sale.order': ('team_id', 'user_id', 'partner_id', 'id'),
    'sale.report': ('team_id', 'user_id', 'partner_id'),
    'crm.lead': ('team_id', 'user_id', 'partner_id', 'id'),
    'project.task': ('project_id', 'user_ids', 'partner_id', 'id'),
    'report.project.task.user': ('project_id', 'user_ids'),
    'project.project': ('id', 'user_id', 'partner_id'),
    'purchase.order': ('user_id', 'partner_id', 'picking_type_id', 'id'),
    'account.move': ('journal_id', 'invoice_user_id', 'partner_id', 'id'),
    'stock.picking': ('picking_type_id', 'user_id', 'partner_id', 'id'),
    'mrp.production': ('picking_type_id', 'user_id', 'product_id', 'id'),
    'helpdesk.ticket': ('team_id', 'user_id', 'partner_id', 'id'),
}
# and on any other data
FILTER_FIRST = (
    'team_id', 'user_id', 'user_ids', 'journal_id', 'warehouse_id', 'picking_type_id', 'project_id',
    'partner_id', 'company_id',
)
# the words of a job name that point to an app, by the module of the app's menu: a
# profile named "Salesman" or "Warehouse Staff" starts with that app ticked. A word
# matches the start of a word of the name ('invoic': Invoice, Invoicing), a word
# ending with a space only as a whole ('lead ': not Leader).
APP_WORDS = {
    'sale': ('sale', 'seller', 'selling'),
    'sale_management': ('sale', 'seller', 'selling'),
    'crm': ('crm ', 'lead ', 'leads ', 'pipeline', 'opportunit'),
    'stock': ('inventor', 'stock', 'warehous', 'storekeep', 'store keeper', 'logistic', 'picker ',
              'picking', 'shipping', 'dispatch'),
    'purchase': ('purchas', 'buyer', 'procure', 'sourcing'),
    'account': ('account', 'invoic', 'billing', 'financ', 'bookkeep', 'treasur', 'payable', 'receivable'),
    'point_of_sale': ('pos ', 'point of sale', 'cashier', 'retail', 'shop '),
    'mrp': ('manufactur', 'production', 'mrp ', 'factory', 'workshop'),
    'project': ('project', 'task'),
    'hr_timesheet': ('timesheet',),
    'hr': ('hr ', 'human resource', 'employee'),
    'hr_holidays': ('time off', 'leave ', 'leaves ', 'holiday'),
    'hr_expense': ('expense',),
    'hr_recruitment': ('recruit', 'hiring'),
    'hr_attendance': ('attendance',),
    'website': ('website', 'webmaster'),
    'website_slides': ('elearning', 'e-learning', 'course', 'trainer'),
    'maintenance': ('maintenance', 'technician'),
    'repair': ('repair',),
    'fleet': ('fleet', 'driver'),
    'event': ('event ', 'events '),
    'survey': ('survey',),
    'mass_mailing': ('marketing', 'mailing'),
    'im_livechat': ('livechat', 'live chat'),
    'calendar': ('calendar',),
    'contacts': ('contact',),
    'project_todo': ('todo', 'to-do'),
}
# an app with no icon of its own: the icon Odoo shows for a module without one
APP_ICON = '/base/static/description/icon.png'

# the data of an app a step asks about: its documents, not every list of it
MAX_DATA = 6


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    def action_guided_setup(self):
        """ Setup Wizard: of this profile, or of a new one when none or several are selected. """
        return {
            'type': 'ir.actions.client',
            'tag': 'om_access_guided_setup',
            'params': {'profile_id': self.id if len(self) == 1 else False},
        }

    #
    # step 1: who
    #

    @api.model
    def om_guided_new(self, name, user_ids):
        """ The profile of a new Setup Wizard: archived until Finish, so its users
        are not restricted by a profile set up halfway. """
        self._om_check_admin()
        name = (name or '').strip()
        if not name:
            raise UserError(_("Give the profile a name."))
        profile = self.create({'name': name, 'active': False, 'user_ids': [Command.set(user_ids or [])]})
        return profile.id

    def om_guided_set_who(self, name, user_ids):
        self._om_check_admin()
        self.ensure_one()
        name = (name or '').strip()
        if not name:
            raise UserError(_("Give the profile a name."))
        values = {}
        if name != self.name:
            values['name'] = name
        if set(user_ids or []) != set(self.user_ids.ids):
            values['user_ids'] = [Command.set(user_ids or [])]
        if values:
            self.write(values)

    #
    # step 2: apps
    #

    def _om_guided_apps(self):
        """ [(app menu, shown, app access info)] of the apps the users of the profile can be given. """
        profile = self.sudo()
        hidden = set(profile.hidden_menu_ids.ids)
        granted = set(profile.granted_group_ids.ids)
        access = profile.om_app_access(profile.user_ids.ids)
        # the apps every internal user opens (Discuss, To-do, Contacts): offered too, to hide
        everyone = self.env['res.groups']
        for xmlid in ('base.group_user', 'base.group_user_regular'):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                everyone |= group | group.all_implied_ids
        result = []
        for root in self.env['ir.ui.menu'].sudo().search([('parent_id', '=', False)]):
            if not (root.child_id or root.action):
                continue
            info = access.get(root.id)
            if root.group_ids and not info and not (root.group_ids & everyone):
                # an app only Settings users open (Settings, Apps): not for a profile to give
                continue
            # with no users yet, an app with groups opens only once the profile gives it
            given = not info or (info['open'] and bool(profile.user_ids)) or bool(set(info['gate_ids']) & granted)
            result.append((root, root.id not in hidden and given, info))
        return result

    def _om_guided_icon(self, root):
        return f'/web/image/ir.ui.menu/{root.id}/web_icon_data' if root.web_icon_data else APP_ICON

    @api.model
    def _om_guided_name_apps(self, name, roots):
        """ The apps a job name points to, among the root menus given: by the name of the
        app ("Project User") or by the words of APP_WORDS ("Salesman", "Warehouse Staff"). """
        def words(value):
            return ' ' + ' '.join(re.findall(r'\w+(?:-\w+)?', (value or '').lower())) + ' '

        text = words(name)
        if not text.strip():
            return []
        # Point of Sale is not Sales
        text_sale = text.replace(' point of sale', ' ')

        def said(word, module=None):
            return f' {word}' in (text_sale if module in ('sale', 'sale_management') else text)

        modules = {module for module, module_words in APP_WORDS.items()
                   if any(said(word, module) for word in module_words)}
        xmlids = roots._get_external_ids()
        result = []
        for root in roots:
            owners = {xmlid.split('.')[0] for xmlid in xmlids.get(root.id, ())}
            if root.web_icon and ',' in root.web_icon:
                owners.add(root.web_icon.split(',')[0])
            names = {words(root.name).strip(), words(root.with_context(lang='en_US').name).strip()}
            if owners & modules or any(said(app_name + ' ') for app_name in names if app_name):
                result.append(root.id)
        return result

    def om_guided_state(self):
        """ What the pop-up starts from. """
        self._om_check_admin()
        self.ensure_one()
        profile = self.sudo()
        described = self.fields_get(list(GUIDED_SWITCHES), ['string', 'help'])
        apps = profile._om_guided_apps()
        return {
            'id': profile.id,
            'name': profile.name,
            'is_draft': not profile.active,
            'user_ids': profile.user_ids.ids,
            'apps': [{
                'id': root.id,
                'name': root.name,
                'icon': profile._om_guided_icon(root),
                'shown': shown,
            } for root, shown, _info in apps],
            # the apps the name of the profile points to: ticked to start a new profile with
            'suggested_ids': self._om_guided_name_apps(
                profile.name, self.env['ir.ui.menu'].sudo().union(*(root for root, _shown, _info in apps))),
            'switches': [{
                'name': name,
                'label': described[name]['string'],
                'help': described[name].get('help') or '',
                'value': bool(profile[name]),
            } for name in GUIDED_SWITCHES if name in described],
        }

    def om_guided_set_apps(self, shown_ids):
        """ The apps the users see: the others are hidden. Ticking an app its users
        cannot open gives it to them, as in the menu tree. """
        self._om_check_admin()
        self.ensure_one()
        shown_ids = set(shown_ids or [])
        Menu = self.env['ir.ui.menu'].sudo()
        Group = self.env['res.groups'].sudo()
        # each app made as answered, whatever it was before: an app hidden only because no user
        # opens it yet must be hidden for good, or the users added later see it
        for root, _shown, info in self._om_guided_apps():
            granted = set(self.granted_group_ids.ids)
            if root.id in shown_ids:
                if root in self.hidden_menu_ids:
                    self.hidden_menu_ids -= root
                opened = info and info['open'] and bool(self.user_ids)
                if info and not opened and not set(info['gate_ids']) & granted:
                    self.granted_group_ids |= Group.browse(info['grant']['id'])
            else:
                if root not in self.hidden_menu_ids:
                    below = Menu.search([('id', 'child_of', root.id)])
                    self.hidden_menu_ids = (self.hidden_menu_ids - below) | root
                given = set(info['group_ids']) & granted if info else set()
                if given:
                    self.granted_group_ids -= Group.browse(list(given))

    #
    # one step for each app
    #

    def _om_guided_data_menus(self, root):
        """ [(menu, model)] of the main data of an app: the first menus opening data the app
        itself brings, outside its configuration. """
        Wizard = self.env['om.access.app.wizard'].new({'profile_id': self.id, 'app_id': root.id})
        candidates, opened = [], {}
        for menu, _depth, config in Wizard._app_menus():
            model_name = not config and menu.action and Wizard._menu_model(menu)
            if (not model_name or self.env[model_name]._transient
                    or model_name.startswith(SIMPLE_FILTER_SKIPPED)):
                continue
            if model_name not in opened:
                candidates.append((menu, model_name))
            opened[model_name] = opened.get(model_name, 0) + 1
        # the documents most menus open first (the invoices and bills before the journals of the
        # dashboard), the reports (views of the database, opened by many Reporting menus) last
        candidates.sort(key=lambda candidate: (not self.env[candidate[1]]._auto, -opened[candidate[1]]))
        modules = Wizard._app_modules()
        creators = Wizard._creating_modules([model_name for _menu, model_name in candidates])
        return [(menu, model_name) for menu, model_name in candidates
                if creators.get(model_name) in modules][:MAX_DATA]

    @api.model
    def _om_guided_filter_fields(self, fields, model_name):
        """ The fields of a simple filter, those people limit this data by most first. """
        names = FILTER_BY_MODEL.get(model_name, ()) + FILTER_FIRST
        first = {}
        for name in names:
            first.setdefault(name, len(first))
        return sorted(fields, key=lambda field: (field['name'] not in first, first.get(field['name'], 0),
                                                 field['name'] == 'id', not field['shown']))

    def _om_guided_linked_from(self, model_name):
        """ The label of the data a record filter follows, when it was limited along with it
        (the tasks of the projects kept: Project), else False. """
        line = self.model_ids.filtered(lambda line: line.model_id.model == model_name)[:1]
        rows = _om_parse_simple_filter(line.domain) if line else None
        if not rows or not all('.' in row['field'] for row in rows):
            return False
        field = self.env[model_name]._fields.get(rows[0]['field'].split('.')[0])
        return field._description_string(self.env) if field is not None else False

    def _om_guided_count(self, model_name):
        """ {'total', 'kept'}: how many records of the data there are, and how many the record filter
        of the profile keeps (False when it depends on the user, or cannot be counted). """
        Model = self.env[model_name].sudo().with_context(active_test=True)
        try:
            total = Model.search_count([])
        except Exception:  # noqa: BLE001 - a count is a hint, never a reason to fail the step
            return False
        line = self.model_ids.filtered(lambda line: line.model_id.model == model_name)[:1]
        domain = (line.domain or '').strip() if line else ''
        if not domain:
            return {'total': total, 'kept': total}
        if re.search(r'\buid\b|\buser\b', domain):
            return {'total': total, 'kept': False}
        try:
            kept = Model.search_count(safe_eval(domain, {}))
        except Exception:  # noqa: BLE001
            _logger.debug("Setup Wizard: cannot count %s with %s", model_name, domain)
            kept = False
        return {'total': total, 'kept': kept}

    def om_guided_set_read_only(self, app_id, value):
        """ Read only in the whole app, or not: the rule of the app menu, never its hidden menus. """
        self._om_check_admin()
        self.ensure_one()
        root = self.env['ir.ui.menu'].sudo().browse(app_id).exists()
        if not root or root.parent_id:
            raise UserError(_("This app no longer exists."))
        rights = (True, not value, not value, not value)
        self._om_set_menu_rights(root, False, dict(zip(PERM_FIELDS, rights)))
        rule = self.menu_rule_ids.filtered(lambda line: line.menu_id == root)
        if not value and rule and rule.records == 'all' and not any(rule[flag] for flag in MODEL_FLAGS):
            # nothing left to say on the app: the rule goes
            rule.unlink()
        return self.om_guided_app(app_id)

    def om_guided_app_set_many(self, app_id, menu_id, changes):
        """ Several changes of reports, buttons or menus at once (allow all, hide all); the step again. """
        self._om_check_admin()
        self.ensure_one()
        menu = self.env['ir.ui.menu'].sudo().browse(menu_id).exists()
        if not menu:
            raise UserError(_("This menu no longer exists."))
        model_name = menu.action and self.env['om.access.app.wizard']._menu_model(menu)
        for change in changes or ():
            kind = change.get('kind')
            if kind not in ('print', 'button', 'hide_menu', 'field', 'element'):
                raise UserError(_("Unknown change: %s", kind))
            getattr(self, f'_om_set_{kind}')(menu, model_name, change)
        return self.om_guided_app(app_id)

    def _om_guided_data_entry(self, menu, model_name):
        """ What a step shows of one data: its records, reports and buttons. """
        entry = self.om_menu_panel(menu.id)
        return {
            'menu_id': menu.id,
            'menu': menu.name,
            'model': model_name,
            'label': entry['model_label'],
            'records': entry['rights']['records'],
            'source': entry['source'],
            'choices': entry['record_choices'],
            'simple_filter': entry['simple_filter'],
            'filter_fields': self._om_guided_filter_fields(entry['filter_fields'], model_name),
            'linked_from': self._om_guided_linked_from(model_name),
            'linked': entry['linked'],
            'count': self._om_guided_count(model_name),
            # what each choice keeps, in words and as its filter: the tooltips of the choices
            'choice_help': self._om_guided_choice_help(model_name),
            # a filter written by hand, shown as it is
            'domain': entry['line_id'] and (self.env['om.access.profile.model'].sudo().browse(
                entry['line_id']).domain or '').strip() or '',
            # with Their warehouse: the users whose Default Warehouse is empty see almost nothing
            'no_warehouse': self._om_guided_no_warehouse(),
            'print': entry['print'],
            # the Fields page: the fields and tabs of the screens, the form to show them on
            **self._om_guided_fields(menu, model_name, entry),
            # the buttons people can name: those of the screen with a text, or already set
            'buttons': [button for button in entry['buttons']
                        if button['mode'] != 'visible' or (
                            button['label'] and button['label'] != button['button_name']
                            and not button['label'].isdigit())],
        }

    def _om_guided_fields(self, menu, model_name, entry):
        """ The fields of a data as its form shows them: the form view to draw, a record to draw it
        on, the fields on the form and those only in its lists or cards, its tabs. """
        action = menu.sudo().action
        own = {}
        if action and action._name == 'ir.actions.act_window':
            own = {view_type: view_id for view_id, view_type in action.views if view_id}
        model = self.env[model_name]
        in_form = set()
        try:
            root = etree.fromstring(model.sudo().get_view(own.get('form'), view_type='form')['arch'])
        except Exception:  # noqa: BLE001 - a data without a form
            root = None
        if root is not None:
            in_form = {node.get('name') for node in root.iter('field') if self._om_top_level(node)}
        # the latest record the menu opens (its filter: invoices, not bills), read as the admin
        # setting it up, and the form opened as the menu opens it (its context: Customer, not Vendor)
        domain, context = [], {}
        if action and action._name == 'ir.actions.act_window':
            eval_context = {'uid': self.env.uid, 'context': dict(self.env.context), 'allowed_company_ids': self.env.companies.ids,
                            'active_id': False, 'active_ids': [], 'active_model': False}
            try:
                domain = safe_eval(action.domain or '[]', eval_context)
                context = safe_eval(action.context or '{}', eval_context)
            except Exception:  # noqa: BLE001 - a domain or context of the action needing more
                domain, context = [], {}
        sample = model
        if root is not None:
            for sample_domain in (domain, []):
                try:
                    sample = model.search(sample_domain, limit=1, order='id desc')
                    break
                except Exception:  # noqa: BLE001 - a domain needing more, or data the admin cannot read
                    sample = model
            # none readable: the form drawn empty
        return {
            'form_context': {key: value for key, value in (context or {}).items()
                             if isinstance(value, (str, int, float, bool)) and not key.startswith('search_default')},
            'form_view_id': own.get('form') or False,
            'has_form': root is not None,
            'sample_id': sample.id or False,
            'fields': [dict(field, in_form=field['name'] in in_form) for field in entry['fields']],
            'tabs': [element for element in entry['elements'] if element['element_type'] == 'page'],
        }

    @api.model
    def _om_guided_choice_help(self, model_name):
        """ {choice: what it keeps, then its filter}, with the names of the fields it uses. """
        model = self.env[model_name]
        presets = self.env['om.access.profile.model']._preset_domains(model_name)

        def label(name):
            field = model._fields.get(name)
            return field._description_string(self.env) if field is not None else name

        owner = next((name for name in OWNER_FIELDS if name in model._fields
                      and model._fields[name].type == 'many2one'
                      and model._fields[name].comodel_name == 'res.users'), None)
        texts = {
            'all': _("No limit: every record their groups allow."),
            'own': _("Only the records where %s is the user.", label(owner)) if owner
                   else _("Only the records of the employee of the user."),
            'team': _("Only the records whose %s the user leads or is a member of.", label('team_id')),
            'company': _("Only the records of no company, or of the companies the user has selected "
                         "in the company switcher."),
            'warehouse': _("Only the records whose %s is the Default Warehouse on the user's form. "
                           "Users without one see almost nothing.", label('warehouse_id')),
            'hierarchy': _("Their own records, and those of the employees under them in the org chart, "
                           "three levels down."),
            'today': _("Only the records created today."),
            'week': _("Only the records created this week."),
            'month': _("Only the records created this month."),
            'year': _("Only the records created this year."),
        }
        result = {'all': texts['all']}
        for key, (field_name, domain) in presets.items():
            if field_name == 'domain' and key in texts:
                result[key] = _("%(text)s\nFilter: %(domain)s", text=texts[key], domain=domain)
        return result

    def _om_guided_no_warehouse(self):
        """ The users of the profile with no Default Warehouse in their company. """
        if 'property_warehouse_id' not in self.env['res.users']._fields:
            return []
        return [user.name for user in self.sudo().user_ids
                if not user.with_company(user.company_id).property_warehouse_id]

    def _om_guided_data_choices(self, root, common):
        """ All the data the menus of an app open, the first menu of each, grouped under
        the menu of the top bar it is in: what the Records page offers to limit. Those
        often limited (``common``) are marked, those limited already too. """
        Wizard = self.env['om.access.app.wizard'].new({'profile_id': self.id, 'app_id': root.id})
        profile = self.sudo()
        lines = {line.model_id.model: line for line in profile.model_ids}
        from_menus = profile.menu_rule_ids._om_rights_by_model()
        result, seen, group = [], set(), ''
        for menu, depth, config in Wizard._app_menus():
            if depth == 1:
                group = menu.name
            model_name = depth and menu.action and Wizard._menu_model(menu)
            if (not model_name or model_name in seen or self.env[model_name]._transient
                    or model_name.startswith(SIMPLE_FILTER_SKIPPED)):
                continue
            seen.add(model_name)
            line = lines.get(model_name)
            limited = (bool(line) and self._om_records_choice(line)[0] != 'all') or bool(
                model_name in from_menus and from_menus[model_name][1])
            result.append({
                'menu_id': menu.id, 'menu': menu.name, 'group': group, 'config': config,
                'model': model_name, 'label': self.env['ir.model']._get(model_name).name,
                'common': model_name in common, 'limited': limited,
            })
        return result

    def om_guided_app(self, menu_id):
        """ The step of one app: its access level, which records of its main data, the records
        it allows (journals, warehouses, shops, teams). """
        self._om_check_admin()
        self.ensure_one()
        root = self.env['ir.ui.menu'].sudo().browse(menu_id).exists()
        if not root or root.parent_id:
            raise UserError(_("This app no longer exists."))
        panel = self.om_menu_panel(root.id)
        hidden = set(self.sudo().hidden_menu_ids.ids)
        Wizard = self.env['om.access.app.wizard'].new({'profile_id': self.id, 'app_id': root.id})
        menus = []
        for menu, depth, config in Wizard._app_menus():
            if not depth:
                continue
            path = [int(part) for part in menu.parent_path.split('/') if part]
            menus.append({
                'id': menu.id, 'name': menu.name, 'depth': depth - 1, 'is_config': config,
                'hidden': menu.id in hidden,
                # hidden with a menu above it: shown unticked, and ticked again with it
                'hidden_above': bool(hidden.intersection(path[:-1])),
            })
        suggested = self._om_guided_data_menus(root)
        data = [self._om_guided_data_entry(menu, model_name) for menu, model_name in suggested]
        # the Records page: all the data of the app to pick from, and a card for each data
        # limited already or picked on the page (the context key om_guided_open)
        choices = self._om_guided_data_choices(root, {model_name for _menu, model_name in suggested})
        opened = set(self.env.context.get('om_guided_open') or ())
        known = {entry['menu_id']: entry for entry in data}
        records = [known.get(choice['menu_id']) or self._om_guided_data_entry(
                       self.env['ir.ui.menu'].sudo().browse(choice['menu_id']), choice['model'])
                   for choice in choices if choice['limited'] or choice['menu_id'] in opened]
        rule = self.menu_rule_ids.filtered(lambda line: line.menu_id == root)
        return {
            'read_only': bool(rule) and rule.perm_read and not (rule.perm_create or rule.perm_write or rule.perm_unlink),
            'app': {
                'id': root.id, 'name': root.name,
                'icon': self._om_guided_icon(root),
            },
            'level': panel.get('level') or False,
            'has_children': bool(root.child_id),
            'allowed': panel.get('allowed') or [],
            'menus': menus,
            'data': data,
            'data_choices': choices,
            'records': records,
        }

    def om_guided_app_set(self, app_id, menu_id, change):
        """ One change of an app step, made as the Configure screen makes it; the step again. """
        self.om_menu_panel_set(menu_id, change)
        if change.get('kind') == 'hide_menu':
            # the menus under it follow it: hidden with it, and all shown again with it, not
            # left unticked on their own from before
            below = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', menu_id), ('id', '!=', menu_id)])
            if below & self.hidden_menu_ids:
                self.hidden_menu_ids -= below
        return self.om_guided_app(app_id)

    #
    # step everywhere, and the review
    #

    def om_guided_set_switch(self, name, value):
        self._om_check_admin()
        self.ensure_one()
        if name not in GUIDED_SWITCHES:
            raise UserError(_("Unknown setting: %s", name))
        if bool(self[name]) != bool(value):
            self[name] = bool(value)

    def om_guided_summary(self):
        """ The profile in a few lines, for the last step. """
        self._om_check_admin()
        self.ensure_one()
        profile = self.sudo()
        apps, hidden_apps = [], []
        for root, shown, _info in profile._om_guided_apps():
            if not shown:
                hidden_apps.append(root.name)
                continue
            step = self.om_guided_app(root.id)
            lines = []
            for entry in step['data']:
                labels = dict(entry['choices'])
                if entry['records'] == 'some' and entry['linked_from']:
                    text = _("those of the %s kept", entry['linked_from'])
                elif entry['records'] == 'some':
                    names = [record['name'] for row in entry['simple_filter'] for record in row['records']]
                    if any(row['me'] for row in entry['simple_filter']):
                        names.append(_("the user"))
                    text = _("only of %s", ", ".join(names))
                elif entry['records'] in ('custom', 'filter'):
                    text = _("a filter of their own")
                elif entry['records'] in labels:
                    text = labels[entry['records']].lower()
                else:
                    continue
                if entry['records'] != 'all':
                    lines.append(_("%(data)s: %(records)s", data=entry['label'], records=text))
            for kind in step['allowed']:
                names = [record['name'] for record in kind['records']]
                if kind['per_user']:
                    names.append(_("those set on each user"))
                if names:
                    lines.append(_("%(kind)s: %(records)s", kind=kind['label'], records=", ".join(names)))
            level = step['level']
            apps.append({
                'name': root.name,
                'level': self._om_guided_level_label(level),
                'lines': lines,
            })
        described = self.fields_get(list(GUIDED_SWITCHES), ['string'])
        return {
            'name': profile.name,
            'users': profile.user_ids.mapped('name'),
            'apps': apps,
            'hidden_apps': hidden_apps,
            'switches': [described[name]['string'] for name in GUIDED_SWITCHES
                         if name in described and profile[name]],
        }

    @api.model
    def _om_guided_level_label(self, level):
        return {
            'full': _("Full access"), 'user': _("No configuration"),
            'readonly': _("Read only"), 'none': _("No access"),
        }.get(level) or _("Set by hand")

    def om_guided_finish(self):
        """ The profile set up: it applies from now on. """
        self._om_check_admin()
        self.ensure_one()
        if not self.active:
            self.active = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def om_guided_discard(self):
        """ Cancel on a new profile: the archived draft goes. """
        self._om_check_admin()
        self.filtered(lambda profile: not profile.active).unlink()
