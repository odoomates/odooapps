import json
import re
from datetime import timedelta

from lxml import etree
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

from .om_usage_stat import HISTORY_WEEKS

PARAM = 'om_adaptive_views.'
DEFAULTS = {
    'learning': True,
    'min_saves': 100,
    'fade_rate': 2.0,
    'promote_rate': 80.0,
    'max_folds': 10,
    'fill_guard': 50.0,
    'min_visits': 50,
    'filter_rate': 70.0,
    'min_column_toggles': 5,
    'days': 90,
    # documents with legal weight keep every field in view
    'protected_models': 'account.move,account.payment,account.bank.statement,res.users,res.company',
    'protected_fields': '',
    # applied on their own
    'auto_apply': False,
    'auto_min_saves': 300,
    'auto_fade_rate': 1.0,
    'auto_min_visits': 150,
    'auto_filter_rate': 85.0,
    # personal default filters
    'user_filters': True,
    'user_min_visits': 20,
    'user_filter_rate': 70.0,
    # menu order
    'menu_order': True,
    'min_menu_opens': 50,
    'menu_ratio': 1.5,
    'user_menus': True,
    'user_min_menu_opens': 30,
}
PREVIEW_KEY = 'om_adapt_preview_view_ref'
# the changes that may be applied without an admin
AUTO_KINDS = ('fade_field', 'show_column', 'hide_column', 'default_filter', 'user_filter')
# the parent of the apps, in the menu order
ROOT_MENU = 'root'
# fields a form is built around, never folded
KEPT_FIELDS = {'name', 'display_name', 'company_id', 'currency_id', 'state', 'active', 'sequence'}
# attributes whose expressions name other fields: a field read there is in use even if nobody edits it
EXPRESSION_ATTRS = ('invisible', 'readonly', 'required', 'column_invisible', 'context', 'domain', 'options')
KEPT_WIDGETS = ('statusbar', 'handle', 'priority', 'boolean_favorite', 'image', 'properties')
TRUE_VALUES = ('1', 'True', 'true')

KINDS = [
    ('fade_field', 'Fold a field'),
    ('promote_field', 'Bring a field forward'),
    ('fold_page', 'Fold a tab'),
    ('show_column', 'Show a column'),
    ('hide_column', 'Hide a column'),
    ('default_filter', 'Default filter'),
    ('hide_filter', 'Hide a filter'),
    ('user_filter', 'Personal default filter'),
    ('menu_order', 'Menu order'),
]
VIEW_TYPE_OF = {
    'fade_field': 'form', 'promote_field': 'form', 'fold_page': 'form',
    'show_column': 'list', 'hide_column': 'list',
    'hide_filter': 'search', 'menu_order': 'menu',
}
KINDS_OF_VIEW = {
    'form': ['fade_field', 'promote_field', 'fold_page'],
    'list': ['show_column', 'hide_column'],
    'search': ['hide_filter'],
}


def param(env, key):
    """ A setting of the module, read with the type of its default. """
    default = DEFAULTS[key]
    Params = env['ir.config_parameter'].sudo()
    getter = {bool: Params.get_bool, int: Params.get_int, float: Params.get_float}.get(type(default), Params.get_str)
    return getter(PARAM + key, default)


def split_list(text):
    return {item.strip() for item in (text or '').split(',') if item.strip()}


def has_class(class_name):
    return 'contains(concat(" ", normalize-space(@class), " "), " %s ")' % class_name


class OmAdaptRule(models.Model):
    """ One change to a screen, learnt from how it is used: suggested, applied or dismissed. """
    _name = 'om.adapt.rule'
    _description = 'Screen change'
    _order = 'state_order, score desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    kind = fields.Selection(KINDS, required=True, readonly=True)
    state = fields.Selection([
        ('suggested', 'Suggested'),
        ('applied', 'Applied'),
        ('dismissed', 'Dismissed'),
    ], default='suggested', required=True, readonly=True)
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, ondelete='cascade',
                                 default=lambda self: self.env.company)
    model = fields.Char(required=True, readonly=True)
    model_label = fields.Char(string='Model name', compute='_compute_model_label')
    view_id = fields.Many2one('ir.ui.view', readonly=True, ondelete='cascade')
    view_type = fields.Selection([('form', 'Form'), ('list', 'List'), ('search', 'Search'), ('menu', 'Menu')],
                                 compute='_compute_view_type', store=True)
    action_id = fields.Many2one('ir.actions.act_window', readonly=True, ondelete='cascade')
    group_id = fields.Many2one(
        'res.groups', string='Role', readonly=True, ondelete='cascade',
        help="The users the change is for; empty for everyone.")
    user_id = fields.Many2one(
        'res.users', string='User', readonly=True, ondelete='cascade',
        help="The one user the change is for, for a personal default filter.")
    element = fields.Char(required=True, readonly=True, help="The technical name of the field, tab or filter.")
    element_label = fields.Char(string='Field, tab or filter', readonly=True)
    filter_domain = fields.Text(readonly=True)
    filter_context = fields.Text(readonly=True)
    filter_id = fields.Many2one('ir.filters', string='Favorite', readonly=True, ondelete='set null')
    uses = fields.Integer(readonly=True, help="How many times the field, filter or column was used.")
    total = fields.Integer(readonly=True, help="Saves of the form, or visits of the action, in the period.")
    score = fields.Float(string='Rate (%)', readonly=True, digits=(16, 1))
    evidence = fields.Char(readonly=True)
    history = fields.Char(string='Weekly use', readonly=True,
                          help="Uses per week over the last weeks, oldest first.")
    last_used = fields.Date(readonly=True)
    menu_order = fields.Char(readonly=True, help="The menus in their learnt order, as a list of IDs.")
    menu_order_display = fields.Text(string='New order', compute='_compute_menu_order_display')
    auto_applied = fields.Boolean(readonly=True, help="Applied on its own, without an admin.")
    applied_date = fields.Datetime(readonly=True)
    journal_ids = fields.One2many('om.adapt.journal', 'rule_id', string='Journal')

    _om_rule_uniq = models.UniqueIndex(
        "(company_id, kind, model, COALESCE(view_id, 0), COALESCE(action_id, 0), "
        "COALESCE(group_id, 0), COALESCE(user_id, 0), element)")

    @api.depends('kind', 'element_label', 'element', 'model')
    def _compute_name(self):
        labels = dict(self._fields['kind']._description_selection(self.env))
        for rule in self:
            rule.name = "%s: %s" % (labels.get(rule.kind), rule.element_label or rule.element)

    @api.depends('state')
    def _compute_state_order(self):
        order = {'suggested': 0, 'applied': 1, 'dismissed': 2}
        for rule in self:
            rule.state_order = order.get(rule.state, 3)

    @api.depends('kind')
    def _compute_view_type(self):
        for rule in self:
            rule.view_type = VIEW_TYPE_OF.get(rule.kind, 'search')

    @api.depends('model')
    def _compute_model_label(self):
        labels = {model.model: model.name for model in self.env['ir.model'].sudo().search(
            [('model', 'in', list(set(self.mapped('model'))))])}
        for rule in self:
            rule.model_label = labels.get(rule.model, rule.model)

    @api.depends('menu_order')
    def _compute_menu_order_display(self):
        for rule in self:
            ids = rule._om_menu_ids()
            menus = {menu.id: menu.name for menu in self.env['ir.ui.menu'].sudo().browse(ids).exists()}
            rule.menu_order_display = '\n'.join(
                '%s. %s' % (position, menus[menu_id])
                for position, menu_id in enumerate((i for i in ids if i in menus), start=1)) or False

    def _om_menu_ids(self):
        try:
            ids = json.loads(self.menu_order or '[]')
        except ValueError:
            return []
        return [i for i in ids if isinstance(i, int)] if isinstance(ids, list) else []

    @api.model
    def _om_param(self, key):
        return param(self.env, key)

    # ------------------------------------------------------------------
    # applying
    # ------------------------------------------------------------------

    def action_apply(self):
        for rule in self.filtered(lambda r: r.state != 'applied'):
            if rule.kind in ('default_filter', 'user_filter'):
                rule._om_create_favorite()
            rule.write({'state': 'applied', 'applied_date': fields.Datetime.now()})
            rule._om_log('apply')
        self._om_changed()
        return True

    def action_undo(self):
        for rule in self.filtered(lambda r: r.state == 'applied'):
            rule.filter_id.unlink()
            rule.state = 'suggested'
            rule._om_log('undo')
        self._om_changed()
        return True

    def action_dismiss(self):
        self.action_undo()
        self.state = 'dismissed'
        for rule in self:
            rule._om_log('dismiss')
        return True

    def action_restore(self):
        self.filtered(lambda r: r.state == 'dismissed').state = 'suggested'
        return True

    def _om_log(self, event):
        """ Keep every change in the journal: who, when, and on what numbers. """
        if event == 'apply' and self.env.context.get('om_adapt_auto'):
            event = 'auto'
        for rule in self:
            self.env['om.adapt.journal'].sudo().create({
                'rule_id': rule.id, 'name': rule.name, 'event': event, 'company_id': rule.company_id.id,
                'model_label': rule.model_label, 'group_id': rule.group_id.id,
                'target_user_id': rule.user_id.id, 'evidence': rule.evidence,
                'uses': rule.uses, 'total': rule.total,
            })

    def _om_favorite_values(self):
        self.ensure_one()
        return {
            'name': self.element_label or self.element,
            'model_id': self.model,
            'action_id': self.action_id.id,
            'domain': self.filter_domain or '[]',
            'context': self.filter_context or '{}',
            'is_default': True,
            'user_ids': [Command.set(self.user_id.ids)],
        }

    def _om_create_favorite(self):
        """ A filter applied on most visits becomes the action's default favorite, shared by all.

        That is Odoo's own mechanism for a default search, so undoing is deleting it.
        """
        self.ensure_one()
        Filters = self.env['ir.filters'].sudo()
        if self.kind == 'user_filter':
            # a person's own default, for nobody else
            taken = Filters.search([('action_id', '=', self.action_id.id), ('is_default', '=', True),
                                    ('user_ids', 'in', self.user_id.ids)], limit=1)
            if taken:
                raise UserError(self.env._("%(user)s already has a default favorite on %(action)s.",
                                           user=self.user_id.name, action=self.action_id.name))
            self.filter_id = Filters.create(self._om_favorite_values())
            return
        taken = Filters.search([('action_id', '=', self.action_id.id), ('is_default', '=', True),
                                ('user_ids', '=', False)], limit=1)
        if taken:
            raise UserError(self.env._(
                "The action %(action)s already has a default favorite shared with everyone (%(favorite)s).",
                action=self.action_id.name, favorite=taken.name))
        self.filter_id = Filters.create(self._om_favorite_values())

    @api.model
    def _om_changed(self):
        """ Views are cached on the server and in every browser: a new version in their cache
        key makes the server build them again, and a notice on the bus makes the open
        browsers drop the copies they hold. """
        Params = self.env['ir.config_parameter'].sudo()
        Params.set_int(PARAM + 'version', Params.get_int(PARAM + 'version', 0) + 1)
        self.env.ref('base.group_user')._bus_send('om_adaptive_views/refresh', {})

    @api.model
    def _om_views_version(self):
        return self.env['ir.config_parameter'].sudo().get_int(PARAM + 'version', 0)

    @api.model
    def _om_current_role(self):
        return self.env['om.usage.stat']._om_user_role(self.env.user)

    @api.model
    def _om_preview_ids(self):
        """ The changes being previewed. The web client only sends the language and the keys
        ending in _view_ref when it loads views, hence the name of the key. """
        value = self.env.context.get(PREVIEW_KEY) or ''
        return tuple(int(part) for part in str(value).split(',') if part.strip().isdigit())

    @api.model
    def _om_view_cache_key(self):
        """ What a view built for the current user depends on, besides the view itself. """
        return (self.env.company.id, self._om_views_version(), self._om_current_role().id or 0,
                self._om_preview_ids())

    @api.model
    def _om_applied_domain(self, model, view_type, view_id):
        return [
            ('company_id', '=', self.env.company.id), ('state', '=', 'applied'),
            ('kind', 'in', KINDS_OF_VIEW.get(view_type, [])), ('model', '=', model),
            ('view_id', 'in', [view_id or False, False]),
            ('group_id', 'in', [False, self._om_current_role().id]), ('user_id', '=', False),
        ]

    @api.model
    def _om_applied(self, model, view_type, view_id):
        """ The rules to apply to one view of one model, for the current user and company,
        and the ones being previewed. """
        if view_type not in KINDS_OF_VIEW:
            return self.browse()
        rules = self.sudo().search(self._om_applied_domain(model, view_type, view_id))
        preview = self._om_preview_ids()
        if preview:
            rules |= self.sudo().browse(preview).exists().filtered(
                lambda r: r.model == model and r.kind in KINDS_OF_VIEW[view_type]
                and r.view_id.id in (view_id, False))
        return rules

    @api.model
    def _om_menu_orders(self):
        """ {parent menu: [menu ids in order]} for the current user: their own order first,
        then their role's, then everyone's. """
        rules = self.sudo().search([
            ('company_id', '=', self.env.company.id), ('state', '=', 'applied'), ('kind', '=', 'menu_order'),
            ('group_id', 'in', [False, self._om_current_role().id]), ('user_id', 'in', [False, self.env.uid]),
        ])
        orders = {}
        for rule in rules.sorted(lambda r: (bool(r.user_id), bool(r.group_id))):
            orders[rule.element] = rule._om_menu_ids()
        return orders

    @api.model
    def _om_apply_arch(self, arch, view_type, rules):
        """ Change a view's architecture for the given rules, in place. """
        # one change per element: a change for a role and the same change for everyone
        seen, unique = set(), self.browse()
        for rule in rules:
            if (rule.kind, rule.element) not in seen:
                seen.add((rule.kind, rule.element))
                unique |= rule
        rules = unique
        if view_type == 'form':
            self._om_apply_form(arch, rules)
        elif view_type == 'list':
            for rule in rules:
                target, value = ('hide', 'show') if rule.kind == 'show_column' else ('show', 'hide')
                for node in arch.xpath('//field[@name=$name][@optional=$target][not(ancestor::field)]',
                                       name=rule.element, target=target):
                    node.set('optional', value)
        elif view_type == 'search':
            for rule in rules.filtered(lambda r: r.kind == 'hide_filter'):
                for node in arch.xpath('//filter[@name=$name]', name=rule.element):
                    node.set('invisible', '1')

    @api.model
    def _om_apply_form(self, arch, rules):
        """ Bring fields forward, fold fields and tabs, and add the link that unfolds them. """
        # the first group of the body of the form: a group placed straight in the sheet, or
        # the first group inside it - never a group of the title block
        anchor = next(iter(arch.xpath('(//sheet/group//group[not(.//group)])[1]')), None)
        if anchor is None:
            anchor = next(iter(arch.xpath('(//sheet/group)[1]')), None)
        for rule in rules.filtered(lambda r: r.kind == 'promote_field'):
            if anchor is None:
                break
            for node in arch.xpath('//page//group/field[@name=$name][not(ancestor::field)]', name=rule.element):
                anchor.append(node)
                break
        folded, tabs = [], 0
        for rule in rules.filtered(lambda r: r.kind == 'fade_field'):
            for node in arch.xpath('//group/field[@name=$name][not(ancestor::field)][not(ancestor::page)]',
                                   name=rule.element):
                node.set('class', ((node.get('class') or '') + ' o_om_faded').strip())
                folded.append(rule.element_label or rule.element)
        for rule in rules.filtered(lambda r: r.kind == 'fold_page'):
            for node in arch.xpath('//page[@name=$name]', name=rule.element):
                node.set('class', ((node.get('class') or '') + ' o_om_faded_page').strip())
                folded.append(self.env._("%s tab", rule.element_label or rule.element))
                tabs += 1
        if not folded:
            return
        container = next(iter(arch.xpath('//sheet')), arch)
        widget = etree.SubElement(container, 'widget')
        widget.set('name', 'om_faded_toggle')
        widget.set('count', str(len(folded) - tabs))
        widget.set('tabs', str(tabs))
        widget.set('labels', ', '.join(folded))

    # ------------------------------------------------------------------
    # learning
    # ------------------------------------------------------------------

    @api.model
    def _om_analyse(self):
        """ Turn the counts of the last weeks into suggestions, for every company. """
        for company in self.env['res.company'].search([]):
            self.with_company(company)._om_analyse_company(company)
        return True

    def action_analyse(self):
        self._om_analyse_company(self.env.company)
        return self.env['ir.actions.act_window']._for_xml_id('om_adaptive_views.action_om_adapt_rule')

    def _om_analyse_company(self, company):
        since = fields.Date.context_today(self) - timedelta(days=self._om_param('days'))
        protected = split_list(self._om_param('protected_models')) | {'om.adapt.rule', 'om.usage.stat'}
        found, field_rows = self._om_find(company, since, protected)
        found += self._om_find_roles(company, since, protected, found)
        kept = self.browse()
        for values in found:
            kept |= self._om_upsert(company, values)
        # a suggestion the numbers no longer support goes; applied and dismissed ones stay
        (self.sudo().search([('company_id', '=', company.id), ('state', '=', 'suggested')]) - kept).unlink()
        self.env['om.adapt.field.report']._om_rebuild(company, field_rows)
        self.env['om.adapt.menu.report']._om_rebuild(company, since)
        self._om_after_analyse(company)

    def _om_find(self, company, since, protected, role=None):
        """ Every change the counts support, for everyone or for one role. """
        found, field_rows = self._om_form_analysis(company, since, protected, role)
        found += self._om_list_analysis(company, since, protected, role)
        found += self._om_search_analysis(company, since, protected, role)
        found += self._om_menu_analysis(company, since, role)
        return found, field_rows

    @api.model
    def _om_key(self, values):
        return (values['kind'], values['model'], values.get('view_id') or False,
                values.get('action_id') or False, values['element'], values.get('menu_order') or False)

    def _om_find_roles(self, company, since, protected, found):
        """ What each role uses differently from everyone: only changes everyone does not get. """
        everyone = {self._om_key(values) for values in found}
        result = []
        for role in company.sudo().om_adapt_role_ids:
            role_found, _rows = self._om_find(company, since, protected, role=role.id)
            for values in role_found:
                if self._om_key(values) not in everyone:
                    values['group_id'] = role.id
                    result.append(values)
        result += self._om_find_user_filters(company, since, protected)
        result += self._om_find_user_menus(company, since)
        return result

    def _om_after_analyse(self, company):
        """ Apply the clearest suggestions on their own, when that is switched on. """
        if not self._om_param('auto_apply'):
            return
        candidates = self.sudo().search([('company_id', '=', company.id), ('state', '=', 'suggested'),
                                         ('kind', 'in', AUTO_KINDS)])
        for rule in candidates.filtered(lambda r: r._om_strong_enough()):
            try:
                with self.env.cr.savepoint():
                    rule.with_context(om_adapt_auto=True).action_apply()
                    rule.auto_applied = True
            except UserError:
                # a favorite already set by a person is kept: their choice wins
                continue

    def _om_strong_enough(self):
        """ Whether a suggestion is clear enough to be applied without an admin. """
        self.ensure_one()
        if self.kind == 'fade_field':
            return (self.total >= self._om_param('auto_min_saves')
                    and self.score <= self._om_param('auto_fade_rate'))
        if self.kind in ('show_column', 'hide_column'):
            return self.uses >= 3 * self._om_param('min_column_toggles')
        if self.kind in ('default_filter', 'user_filter'):
            min_visits = self._om_param('auto_min_visits' if self.kind == 'default_filter' else 'user_min_visits')
            return self.total >= min_visits and self.score >= self._om_param('auto_filter_rate')
        return False

    def _om_identity(self, company, values):
        return [
            ('company_id', '=', company.id), ('kind', '=', values['kind']), ('model', '=', values['model']),
            ('view_id', '=', values.get('view_id') or False), ('action_id', '=', values.get('action_id') or False),
            ('group_id', '=', values.get('group_id') or False), ('user_id', '=', values.get('user_id') or False),
            ('element', '=', values['element']),
        ]

    def _om_upsert(self, company, values):
        """ Keep one rule per change: refresh the numbers, never undo a choice already made. """
        rule = self.sudo().search(self._om_identity(company, values), limit=1)
        refreshed = ('uses', 'total', 'score', 'evidence', 'element_label', 'history', 'last_used')
        if rule:
            # an order already applied stays as it was applied; a suggested one follows the counts
            if rule.state == 'suggested':
                refreshed += ('menu_order',)
            rule.write({key: values[key] for key in refreshed if key in values})
            return rule
        return self.sudo().create(dict(values, company_id=company.id))

    def _om_raw_arch(self, model, view_type, view_id):
        """ The view as Odoo builds it, without the changes this module makes. """
        Model = self.env[model].with_context(om_adapt_raw=True)
        try:
            arch, view = Model._get_view(view_id or None, view_type)
        except (ValueError, AttributeError, UserError):
            return None, None
        return arch, view

    def _om_filled_share(self, model, name):
        """ The share of records that hold a value in a field: a field most records fill was
        filled once, at creation, and is not unused. """
        Model = self.env[model].sudo().with_context(active_test=False)
        try:
            total = Model.search_count([])
            if not total:
                return 0.0
            return 100.0 * Model.search_count([(name, '!=', False)]) / total
        except (ValueError, UserError):
            return 100.0

    def _om_kept_reason(self, model, node, referenced, protected_fields):
        """ Why a field of a form must stay where it is, or '' when it may move. """
        field = self.env[model]._fields.get(node.get('name'))
        name = node.get('name')
        if not field:
            return self.env._("Not a field")
        if name in KEPT_FIELDS or name in protected_fields or f'{model}.{name}' in protected_fields:
            return self.env._("Protected")
        if name in referenced:
            return self.env._("Other fields depend on it")
        if node.xpath('ancestor::div[%s]' % has_class('oe_title')):
            return self.env._("In the title")
        if field.required or node.get('required') not in (None, '0', 'False', 'false'):
            return self.env._("Required")
        if field.readonly or node.get('readonly') in TRUE_VALUES:
            return self.env._("Read-only")
        if node.get('invisible') in TRUE_VALUES:
            return self.env._("Hidden")
        if field.type in ('one2many', 'html') or node.get('widget') in KEPT_WIDGETS:
            return self.env._("Content of the form")
        return ''

    def _om_form_analysis(self, company, since, protected, role):
        """ Fold the fields and tabs nobody edits, bring forward the ones everybody edits. """
        Stats = self.env['om.usage.stat']
        totals = Stats._om_totals(company, since, 'form', ['save', 'edit'], role)
        weekly = Stats._om_weekly(company, 'form', ['edit'], role)
        min_saves = self._om_param('min_saves')
        fade_rate = self._om_param('fade_rate')
        promote_rate = self._om_param('promote_rate')
        max_folds = self._om_param('max_folds')
        fill_guard = self._om_param('fill_guard')
        protected_fields = split_list(self._om_param('protected_fields'))
        saves, edits = {}, {}
        for (model, view_id, _action, element, event), count in totals.items():
            if event == 'save':
                saves[model, view_id] = saves.get((model, view_id), 0) + count
            else:
                edits[model, view_id, element] = count
        depends = self.env._("Other fields depend on it")
        found, rows = [], []
        for (model, view_id), saved in saves.items():
            if model in protected or model not in self.env:
                continue
            arch, view = self._om_raw_arch(model, 'form', view_id)
            if arch is None:
                continue
            referenced = set()
            for node in arch.iter():
                for attr in EXPRESSION_ATTRS:
                    if node.get(attr):
                        referenced.update(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', node.get(attr)))
            base = {'model': model, 'view_id': view.id if view else False}
            if role is not None:
                base['group_id'] = role
            share_of = {}
            folds = []
            seen = set()
            for node in arch.xpath('//field[not(ancestor::field)][not(ancestor::header)]'):
                name = node.get('name')
                if name in seen:
                    continue
                seen.add(name)
                field = self.env[model]._fields.get(name)
                used = edits.get((model, view_id, name), 0)
                share = 100.0 * used / saved
                share_of[name] = share
                page = next(iter(node.xpath('ancestor::page[1]')), None)
                reason = self._om_kept_reason(model, node, referenced, protected_fields)
                history, last_used = weekly.get((model, view_id, 0, name), (Stats._om_no_history(), False))
                in_main_group = node.getparent().tag == 'group' and page is None
                label = node.get('string') or (field.string if field else name)
                if role is None:
                    page_label = (page.get('string') or page.get('name') or '') if page is not None else ''
                    rows.append(dict(base, field_name=name, field_label=label, page_label=page_label,
                                     saves=saved, edits=used, share=share, history=history, last_used=last_used,
                                     kept_reason=reason, foldable=in_main_group and not reason,
                                     status='kept' if reason else 'unused' if not used
                                     else 'rare' if share < fade_rate else 'used'))
                # a field others depend on stays in sight, but may move to where it is used
                movable = not reason or reason == depends
                if saved < min_saves or not movable:
                    continue
                evidence = self.env._("Changed in %(used)s of %(saved)s saves", used=used, saved=saved)
                values = dict(base, element=name, element_label=label, uses=used, total=saved,
                              score=share, evidence=evidence, history=history, last_used=last_used)
                if in_main_group and share < fade_rate and not reason:
                    folds.append(dict(values, kind='fade_field'))
                elif page is not None and node.getparent().tag == 'group' and share >= promote_rate:
                    found.append(dict(values, kind='promote_field'))
            # the rarest first, and never more than the limit: a form is not emptied
            folds.sort(key=lambda v: v['score'])
            for values in folds[:max_folds]:
                if self._om_filled_share(model, values['element']) <= fill_guard:
                    found.append(values)
            if saved >= min_saves:
                found += self._om_page_folds(model, arch, base, saved, share_of, fade_rate)
        return found, rows

    def _om_page_folds(self, model, arch, base, saved, share_of, fade_rate):
        """ Tabs whose fields nobody edits fold away whole. The first tab of a notebook, a tab
        holding lines, and tabs without a name are kept. """
        found = []
        fields_info = self.env[model]._fields
        for notebook in arch.xpath('//notebook'):
            for index, page in enumerate(notebook.xpath('./page')):
                name = page.get('name')
                if index == 0 or not name or page.get('invisible') in TRUE_VALUES:
                    continue
                names = [node.get('name') for node in page.xpath('.//field[not(ancestor::field)]')]
                known = [fields_info[n] for n in names if n in fields_info]
                if not known or any(field.type == 'one2many' or field.required for field in known):
                    continue
                if any(share_of.get(n, 0.0) >= fade_rate for n in names):
                    continue
                used = sum(round(share_of.get(n, 0.0) * saved / 100.0) for n in names)
                found.append(dict(base, kind='fold_page', element=name,
                                  element_label=page.get('string') or name, uses=used, total=saved,
                                  score=100.0 * used / saved, history=self.env['om.usage.stat']._om_no_history(),
                                  last_used=False,
                                  evidence=self.env._("Its %(count)s fields changed in %(used)s of %(saved)s saves",
                                                      count=len(names), used=used, saved=saved)))
        return found

    def _om_list_analysis(self, company, since, protected, role):
        """ Optional columns switched on, or off, more often than the other way round. """
        Stats = self.env['om.usage.stat']
        totals = Stats._om_totals(company, since, 'list', ['column_on', 'column_off'], role)
        weekly = Stats._om_weekly(company, 'list', ['column_on', 'column_off'], role)
        threshold = self._om_param('min_column_toggles')
        balance = {}
        for (model, view_id, _action, element, event), count in totals.items():
            delta = count if event == 'column_on' else -count
            balance[model, view_id, element] = balance.get((model, view_id, element), 0) + delta
        found = []
        for (model, view_id, element), net in balance.items():
            if abs(net) < threshold or model in protected or model not in self.env:
                continue
            arch, view = self._om_raw_arch(model, 'list', view_id)
            if arch is None:
                continue
            optional = 'hide' if net > 0 else 'show'
            node = next(iter(arch.xpath('//field[@name=$name][@optional=$optional][not(ancestor::field)]',
                                        name=element, optional=optional)), None)
            if node is None:
                continue
            field = self.env[model]._fields.get(element)
            history, last_used = weekly.get((model, view_id, 0, element), ('[]', False))
            values = {
                'kind': 'show_column' if net > 0 else 'hide_column', 'model': model,
                'view_id': view.id if view else False, 'element': element,
                'element_label': node.get('string') or (field.string if field else element),
                'uses': abs(net), 'total': abs(net), 'score': 100.0, 'history': history, 'last_used': last_used,
                'evidence': (self.env._("Switched on %(net)s times more than off", net=net) if net > 0
                             else self.env._("Switched off %(net)s times more than on", net=-net)),
            }
            if role is not None:
                values['group_id'] = role
            found.append(values)
        return found

    def _om_action_defaults(self, action):
        """ The filters an action opens with, or None when its context cannot be read. """
        try:
            context = safe_eval(action.context or '{}', {'uid': self.env.uid, 'context': {},
                                                          'allowed_company_ids': [], 'active_id': False})
        except ValueError:
            return None
        return {key[len('search_default_'):] for key in context if key.startswith('search_default_')}

    def _om_search_analysis(self, company, since, protected, role):
        """ The filter applied on most visits becomes the default; filters never used are hidden. """
        Stats = self.env['om.usage.stat']
        totals = Stats._om_totals(company, since, 'search', ['visit', 'filter'], role)
        weekly = Stats._om_weekly(company, 'search', ['filter'], role)
        min_visits = self._om_param('min_visits')
        rate = self._om_param('filter_rate')
        visits, uses = {}, {}
        for (model, _view, action_id, element, event), count in totals.items():
            if event == 'visit':
                visits[model, action_id] = visits.get((model, action_id), 0) + count
            else:
                uses[model, action_id, element] = count
        found = []
        per_search_view = {}
        for (model, action_id), visited in visits.items():
            if model in protected or model not in self.env:
                continue
            action = self.env['ir.actions.act_window'].sudo().browse(action_id).exists()
            if not action or action.res_model != model:
                continue
            defaults = self._om_action_defaults(action)
            arch, search_view = self._om_raw_arch(model, 'search', action.search_view_id.id)
            if arch is None:
                continue
            used_here = {element: used for (umodel, uaction, element), used in uses.items()
                         if (umodel, uaction) == (model, action_id)}
            # the default filter: only for actions that open without filters of their own
            if visited >= min_visits and defaults == set():
                for element, used in used_here.items():
                    if 100.0 * used / visited < rate:
                        continue
                    node = next(iter(arch.xpath('//filter[@name=$name]', name=element)), None)
                    if node is None or node.get('date'):
                        continue
                    history, last_used = weekly.get((model, 0, action_id, element), ('[]', False))
                    values = {
                        'kind': 'default_filter', 'model': model, 'action_id': action.id,
                        'element': element, 'element_label': node.get('string') or element,
                        'filter_domain': node.get('domain') or '[]',
                        'filter_context': node.get('context') or '{}',
                        'uses': used, 'total': visited, 'score': min(100.0 * used / visited, 100.0),
                        'history': history, 'last_used': last_used,
                        'evidence': self.env._("Applied in %(used)s of %(visited)s visits",
                                               used=used, visited=visited),
                    }
                    if role is not None:
                        values['group_id'] = role
                    found.append(values)
            key = (model, search_view.id if search_view else 0)
            entry = per_search_view.setdefault(key, {'visits': 0, 'used': set(), 'defaults': set(), 'arch': arch})
            entry['visits'] += visited
            entry['defaults'] |= defaults or set()
            entry['used'] |= set(used_here)
        # filters nobody switched on in all the visits of every action sharing the search view
        for (model, view_id), entry in per_search_view.items():
            if entry['visits'] < min_visits or not view_id:
                continue
            for node in entry['arch'].xpath('//filter[@name][not(ancestor::searchpanel)]'):
                name = node.get('name')
                if (name in entry['used'] or name in entry['defaults'] or node.get('date')
                        or node.get('invisible') in TRUE_VALUES):
                    continue
                values = {
                    'kind': 'hide_filter', 'model': model, 'view_id': view_id, 'element': name,
                    'element_label': node.get('string') or name, 'uses': 0, 'total': entry['visits'],
                    'score': 0.0, 'history': Stats._om_no_history(), 'last_used': False,
                    'evidence': self.env._("Not used in %(visits)s visits", visits=entry['visits']),
                }
                if role is not None:
                    values['group_id'] = role
                found.append(values)
        return found

    # ------------------------------------------------------------------
    # personal default filters
    # ------------------------------------------------------------------

    def _om_find_user_filters(self, company, since, protected):
        """ The filter one person applies on most of their visits becomes their own default. """
        if not self._om_param('user_filters'):
            return []
        totals = self.env['om.usage.user.stat']._om_user_totals(company, since, ('visit', 'filter'))
        min_visits = self._om_param('user_min_visits')
        rate = self._om_param('user_filter_rate')
        visits, uses = {}, {}
        for (user_id, model, action_id, element, event), count in totals.items():
            if event == 'visit':
                visits[user_id, model, action_id] = visits.get((user_id, model, action_id), 0) + count
            else:
                uses[user_id, model, action_id, element] = count
        found = []
        for (user_id, model, action_id, element), used in uses.items():
            visited = visits.get((user_id, model, action_id), 0)
            if visited < min_visits or model in protected or model not in self.env or 100.0 * used / visited < rate:
                continue
            action = self.env['ir.actions.act_window'].sudo().browse(action_id).exists()
            if not action or action.res_model != model or self._om_action_defaults(action) != set():
                continue
            arch, _view = self._om_raw_arch(model, 'search', action.search_view_id.id)
            node = next(iter(arch.xpath('//filter[@name=$name]', name=element)), None) if arch is not None else None
            if node is None or node.get('date'):
                continue
            found.append({
                'kind': 'user_filter', 'model': model, 'action_id': action.id, 'user_id': user_id,
                'element': element, 'element_label': node.get('string') or element,
                'filter_domain': node.get('domain') or '[]', 'filter_context': node.get('context') or '{}',
                'uses': used, 'total': visited, 'score': min(100.0 * used / visited, 100.0),
                'evidence': self.env._("Applied in %(used)s of their %(visited)s visits", used=used, visited=visited),
            })
        return found

    # ------------------------------------------------------------------
    # menu order
    # ------------------------------------------------------------------

    @api.model
    def _om_menu_children(self):
        """ {parent: [menus in their own order]}, the apps under ROOT_MENU. """
        children = {}
        for menu in self.env['ir.ui.menu'].sudo().search([]):
            children.setdefault(str(menu.parent_id.id) if menu.parent_id else ROOT_MENU, []).append(menu.id)
        return children

    @api.model
    def _om_learn_order(self, ids, opens, pinned):
        """ Move a menu before the one above it only when it is opened clearly more: by the
        ratio set, and by at least five opens. Pinned menus keep their place, and nothing
        moves past them. """
        ratio = self._om_param('menu_ratio')

        def ahead(first, second):
            return opens.get(second, 0) >= ratio * opens.get(first, 0) and opens.get(second, 0) - opens.get(first, 0) >= 5

        def sort(segment):
            segment, moved = list(segment), True
            while moved:
                moved = False
                for index in range(len(segment) - 1):
                    if ahead(segment[index], segment[index + 1]):
                        segment[index], segment[index + 1] = segment[index + 1], segment[index]
                        moved = True
            return segment

        result, segment = [], []
        for menu_id in ids:
            if menu_id in pinned:
                result += sort(segment) + [menu_id]
                segment = []
            else:
                segment.append(menu_id)
        return result + sort(segment)

    @api.model
    def _om_order_values(self, parent, order, opens, children_names, weekly=None):
        Menu = self.env['ir.ui.menu'].sudo()
        label = self.env._("Apps") if parent == ROOT_MENU else Menu.browse(int(parent)).complete_name
        total = sum(opens.get(menu_id, 0) for menu_id in order)
        top = ', '.join('%s %s' % (children_names[menu_id], opens.get(menu_id, 0)) for menu_id in order[:3])
        values = {
            'kind': 'menu_order', 'model': 'ir.ui.menu', 'element': parent, 'element_label': label,
            'menu_order': json.dumps(order), 'uses': total, 'total': total, 'score': 100.0,
            'evidence': self.env._("Opened most: %s", top),
        }
        if weekly:
            values['history'], values['last_used'] = weekly
        return values

    @api.model
    def _om_menu_suggestions(self, opens_of, min_opens, weekly_of=None):
        """ The new orders the opens support. ``opens_of`` counts each menu on its own; a menu
        with menus under it counts as opened whenever one of them is. """
        children = self._om_menu_children()
        pinned = set(self.env.company.sudo().om_adapt_pinned_menu_ids.ids)
        names = {menu.id: menu.name for menu in self.env['ir.ui.menu'].sudo().search([])}
        subtree = {}

        def opened(menu_id):
            if menu_id not in subtree:
                subtree[menu_id] = opens_of.get(menu_id, 0) + sum(opened(c) for c in children.get(str(menu_id), []))
            return subtree[menu_id]

        series_of = {}

        def series(menu_id):
            """ The weekly opens of a menu and the menus under it. """
            if menu_id not in series_of:
                own = json.loads(weekly_of[menu_id][0]) if weekly_of and menu_id in weekly_of else []
                total = own or [0] * HISTORY_WEEKS
                for child in children.get(str(menu_id), []):
                    total = [a + b for a, b in zip(total, series(child))]
                series_of[menu_id] = total
            return series_of[menu_id]

        found = []
        for parent, ids in children.items():
            if len(ids) < 2:
                continue
            opens = {menu_id: opened(menu_id) for menu_id in ids}
            if sum(opens.values()) < min_opens:
                continue
            order = self._om_learn_order(ids, opens, pinned)
            if order == ids:
                continue
            weekly = None
            if weekly_of is not None:
                total = [0] * HISTORY_WEEKS
                for menu_id in ids:
                    total = [a + b for a, b in zip(total, series(menu_id))]
                under, todo = set(), list(ids)
                while todo:
                    menu_id = todo.pop()
                    under.add(menu_id)
                    todo += children.get(str(menu_id), [])
                last = max((weekly_of[m][1] for m in under & set(weekly_of) if weekly_of[m][1]), default=False)
                weekly = (json.dumps(total), last)
            found.append(self._om_order_values(parent, order, opens, names, weekly))
        return found

    def _om_menu_analysis(self, company, since, role):
        """ The menus of each app, and the apps, in the order they are opened. """
        if not self._om_param('menu_order'):
            return []
        Stats = self.env['om.usage.stat']
        opens = {}
        for (_model, _view, _action, element, _event), count in Stats._om_totals(
                company, since, 'menu', ['menu'], role).items():
            if element.isdigit():
                opens[int(element)] = opens.get(int(element), 0) + count
        weekly = {int(key[3]): value for key, value in Stats._om_weekly(company, 'menu', ['menu'], role).items()
                  if key[3].isdigit()}
        found = self._om_menu_suggestions(opens, self._om_param('min_menu_opens'), weekly)
        if role is not None:
            for values in found:
                values['group_id'] = role
        return found

    def _om_find_user_menus(self, company, since):
        """ Each person's own menu order, from the menus they open. """
        if not self._om_param('menu_order') or not self._om_param('user_menus'):
            return []
        per_user = {}
        for (user_id, _model, _action, element, _event), count in self.env['om.usage.user.stat']._om_user_totals(
                company, since, ('menu',)).items():
            if element.isdigit():
                per_user.setdefault(user_id, {})[int(element)] = count
        found = []
        min_opens = self._om_param('user_min_menu_opens')
        for user_id, opens in per_user.items():
            user = self.env['res.users'].sudo().browse(user_id).exists()
            if not user or user.share:
                continue
            for values in self._om_menu_suggestions(opens, min_opens):
                values['user_id'] = user_id
                values['evidence'] = self.env._("Their opens: %s", values['evidence'].split(': ', 1)[-1])
                found.append(values)
        return found

    # ------------------------------------------------------------------
    # preview, digest
    # ------------------------------------------------------------------

    def action_preview(self):
        """ Open the screen with this change, without applying it. """
        self.ensure_one()
        context = {PREVIEW_KEY: str(self.id)}
        if self.view_type == 'form':
            record = self.env[self.model].search([], limit=1)
            if not record:
                raise UserError(self.env._("There is no record to preview the change on."))
            return {
                'type': 'ir.actions.act_window', 'res_model': self.model, 'res_id': record.id,
                'view_mode': 'form', 'views': [(self.view_id.id, 'form')], 'target': 'current',
                'name': self.env._("Preview: %s", self.name), 'context': context,
            }
        if self.view_type == 'list':
            return {
                'type': 'ir.actions.act_window', 'res_model': self.model, 'view_mode': 'list',
                'views': [(self.view_id.id, 'list')], 'target': 'current',
                'name': self.env._("Preview: %s", self.name), 'context': context,
            }
        raise UserError(self.env._("Filters and menus show their effect once applied; apply and undo to try them."))

    @api.model
    def _om_send_digest(self):
        """ Once a week, tell the admins of each company what changed on their screens. """
        since = fields.Datetime.now() - timedelta(days=7)
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url')
        for company in self.env['res.company'].search([]):
            entries = self.env['om.adapt.journal'].sudo().search(
                [('company_id', '=', company.id), ('create_date', '>=', since)], order='id')
            if not entries:
                continue
            admins = self.env.ref('base.group_system').all_user_ids.filtered(
                lambda u: company in u.company_ids and u.email and u.active)
            if not admins:
                continue
            events = dict(entries._fields['event']._description_selection(self.env))
            lines = Markup('').join(
                Markup('<li>%s - <a href="%s/odoo/action-om_adaptive_views.action_om_adapt_rule/%s">%s</a> (%s)</li>') % (
                    events.get(entry.event), base_url, entry.rule_id.id or '', entry.name, entry.evidence or '')
                for entry in entries)
            body = Markup('<p>%s</p><ul>%s</ul><p>%s</p>') % (
                self.env._("The screens of %s changed this week:", company.name), lines,
                self.env._("Each change can be undone from its page."))
            self.env['mail.mail'].sudo().create({
                'subject': self.env._("Adaptive Views: %s changes this week", len(entries)),
                'body_html': body,
                'email_to': ','.join(admins.mapped('email')),
                'auto_delete': True,
            })
        return True
