# Access profile: the single screen the administrator edits, and the resolver
# every enforcement hook of this module reads from.
import ast
import ipaddress
import re
import json
import logging

import pytz
from lxml import etree

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import frozendict
from dateutil.relativedelta import relativedelta
from odoo.tools.safe_eval import datetime as safe_eval_datetime, time as safe_eval_time

from .om_access_allowed import ALLOWED_KINDS
from .conditions import condition_domain, condition_fields
from .value_filters import and_domains, names_read, or_domains
from .login_tools import parse_networks

from .om_access_profile_model import DOMAIN_FIELD_OF_OPERATION, DOMAIN_FIELDS

_logger = logging.getLogger(__name__)

OPERATIONS = ('read', 'write', 'create', 'unlink')
OPERATION_INDEX = {operation: index for index, operation in enumerate(OPERATIONS)}
PERM_FIELDS = ('perm_read', 'perm_write', 'perm_create', 'perm_unlink')

# Never restricted: locking them out would leave the database with no way back in.
EXEMPT_USER_XMLIDS = ('base.user_root', 'base.user_admin')

# A global switch and the per model flag it forces on every model.
GLOBAL_FLAG_OF_MODEL_FLAG = {
    'hide_chatter': 'hide_chatter_all',
    'hide_export': 'block_export',
    'hide_import': 'block_import',
    'hide_archive': 'block_archive',
    'hide_duplicate': 'block_duplicate',
    'hide_print': 'hide_print_all',
    'hide_action_menu': 'hide_action_menu_all',
    'hide_send_message': 'hide_send_message_all',
    'hide_followers': 'hide_followers_all',
    'hide_attachments': 'hide_attachments_all',
}
# chatter parts a profile can hide, and the form class read by chatter_parts.scss
CHATTER_CLASSES = (
    ('hide_send_message', 'o_om_hide_send_message'),
    ('hide_followers', 'o_om_hide_followers'),
    ('hide_attachments', 'o_om_hide_attachments'),
)
MODEL_FLAGS = tuple(GLOBAL_FLAG_OF_MODEL_FLAG)
GLOBAL_FLAGS = (
    'global_readonly', 'hide_chatter_all', 'block_export', 'block_import',
    'block_archive', 'block_duplicate', 'hide_activities', 'hide_settings_menu',
    'lock_statusbar', 'block_rpc', 'block_developer_mode', 'block_login',
    'hide_print_all', 'hide_action_menu_all', 'hide_send_message_all', 'hide_followers_all',
    'hide_attachments_all', 'single_session', 'block_custom_filter', 'block_custom_group',
    'block_favorites', 'block_properties', 'block_apps',
)
# switches of the search bar and the forms, hidden in the web client by a class
# on the body (static/src/search) and, where it writes, refused on the server
BODY_CLASSES = {
    'block_custom_filter': 'o_om_no_custom_filter',
    'block_custom_group': 'o_om_no_custom_group',
    'block_favorites': 'o_om_no_favorites',
    'block_properties': 'o_om_no_properties',
}

FIELD_MODES = (None, 'required', 'readonly', 'hide')  # ordered by severity
HIDE_MODES = ('hide', 'hide_block')
BLOCK_MODES = ('block', 'hide_block')
# what the hidden group of a profile carries (_group_values)
GROUP_FIELDS = frozenset({'name', 'user_ids', 'active', 'company_id', 'granted_group_ids'})
# never granted by a profile: they would make its users administrators, or
# access managers, beyond what the profile itself can undo
UNGRANTABLE_GROUPS = ('base.group_system', 'base.group_erp_manager', 'om_access_manager.group_access_manager',
                      'base.group_portal', 'base.group_public')

# Fields hidden by two switches; those of apps not installed are skipped. The
# values still appear in reports (a quotation PDF): hide those reports too.
COST_FIELDS = (
    ('product.template', 'standard_price'),
    ('product.product', 'standard_price'),
    ('product.product', 'avg_cost'),
    ('product.product', 'total_value'),
    ('sale.order', 'margin'),
    ('sale.order', 'margin_percent'),
    ('sale.order.line', 'purchase_price'),
    ('sale.order.line', 'margin'),
    ('sale.order.line', 'margin_percent'),
    ('pos.order', 'margin'),
    ('pos.order', 'margin_percent'),
    ('pos.order.line', 'total_cost'),
    ('pos.order.line', 'margin'),
    ('pos.order.line', 'margin_percent'),
    ('stock.quant', 'value'),
    ('stock.move', 'price_unit'),
    ('stock.move', 'value'),
    ('stock.move', 'remaining_value'),
    ('product.value', 'value'),
    ('product.value', 'old_value'),
    ('product.value', 'new_value'),
    ('product.value', 'current_value'),
)
SALE_PRICE_FIELDS = (
    ('product.template', 'list_price'),
    ('product.product', 'lst_price'),
    ('sale.order', 'amount_untaxed'),
    ('sale.order', 'amount_tax'),
    ('sale.order', 'amount_total'),
    ('sale.order', 'tax_totals'),
    ('sale.order.line', 'price_unit'),
    ('sale.order.line', 'price_subtotal'),
    ('sale.order.line', 'price_tax'),
    ('sale.order.line', 'price_total'),
    ('sale.order.line', 'price_reduce_taxexcl'),
    ('sale.order.line', 'price_reduce_taxinc'),
    ('sale.order.line', 'discount'),
)
FIELD_SWITCHES = (('hide_costs', COST_FIELDS), ('hide_sale_prices', SALE_PRICE_FIELDS))

# the tags that start a view (or the nested view of an x2many), and those where
# a hidden field is removed rather than made invisible
VIEW_ROOTS = frozenset({
    'form', 'list', 'tree', 'kanban', 'search', 'graph', 'pivot', 'calendar', 'gantt',
    'cohort', 'map', 'activity', 'hierarchy',
})
REMOVED_IN_VIEWS = frozenset({'search', 'graph', 'pivot', 'cohort', 'gantt', 'map'})
FIELD_OPTIONS = ('no_open', 'no_create', 'no_export')

ACTIVITY_FIELDS = frozenset({'activity_ids', 'activity_state', 'activity_date_deadline'})
ACTIVITY_WIDGETS = frozenset({'list_activity', 'mail_activity'})

# the global switches that make a view worth rewriting
VIEW_FLAGS = frozenset({
    'hide_chatter_all', 'block_export', 'block_import', 'block_archive',
    'block_duplicate', 'hide_activities', 'lock_statusbar',
    'hide_send_message_all', 'hide_followers_all', 'hide_attachments_all',
})


def or_conditions(conditions):
    """ Join conditions ('True', 'False' or an expression) with or. """
    if 'True' in conditions:
        return 'True'
    conditions = [condition for condition in conditions if condition != 'False']
    if not conditions:
        return 'False'
    return conditions[0] if len(conditions) == 1 else ' or '.join('(%s)' % c for c in conditions)


def and_conditions(conditions):
    if 'False' in conditions:
        return 'False'
    conditions = [condition for condition in conditions if condition != 'True']
    if not conditions:
        return 'True'
    return conditions[0] if len(conditions) == 1 else ' and '.join('(%s)' % c for c in conditions)


class ProfileRules:
    """ The rules of one profile, frozen and free of any recordset.

    Instances end up in the ormcache, which outlives the cursor they were built
    with, so nothing here may hold an environment.
    """
    __slots__ = ('id', 'name', 'flags', 'perms', 'domains', 'menus', 'buttons',
                 'field_modes', 'field_options', 'field_domains', 'elements',
                 'reports', 'actions', 'model_flags', 'home_action',
                 'login_slots', 'login_tz', 'networks', 'field_conditions', 'element_conditions',
                 'sources')

    def __init__(self, id, name, flags, perms, domains, menus, buttons,
                 field_modes, field_options, field_domains, elements,
                 reports, actions, model_flags, home_action=None,
                 login_slots=(), login_tz='UTC', networks=(), field_conditions=None,
                 element_conditions=None, sources=None):
        self.id = id
        self.name = name
        self.flags = flags                # frozenset of global flag names
        self.perms = perms                # {model: (read, write, create, unlink)}
        self.domains = domains            # {(model, operation): (terms...)}
        self.menus = menus                # frozenset of menu ids, descendants included
        self.buttons = buttons            # tuple of button rules
        self.field_modes = field_modes    # {(model, field): mode}
        self.field_options = field_options  # {(model, field): frozenset}
        self.field_domains = field_domains  # {(model, field): domain string}
        self.elements = elements          # frozenset of (model, type, name)
        self.reports = reports            # frozenset of ir.actions.report ids
        self.actions = actions            # frozenset of action ids (server or window)
        self.model_flags = model_flags    # {model: frozenset of model flag names}
        self.home_action = home_action    # window action id, or None
        self.login_slots = login_slots    # ((weekday, hour_from, hour_to), ...)
        self.login_tz = login_tz
        self.networks = networks          # (ipaddress network, ...)
        # the rules that only apply when a condition holds
        self.field_conditions = field_conditions or {}      # {(model, field): ((mode, condition), ...)}
        self.element_conditions = element_conditions or {}  # {(model, 'page', name): condition}
        self.sources = sources or {}      # {model: names of the menus its rights come from}

    def login_refusal(self, now, address):
        """ Why this profile refuses a sign-in at ``now`` (aware, UTC) from
        ``address``, or None. """
        if self.login_slots:
            local = now.astimezone(pytz.timezone(self.login_tz or 'UTC'))
            hour = local.hour + local.minute / 60
            if not any(day == local.weekday() and start <= hour < end
                       for day, start, end in self.login_slots):
                return 'hours'
        if self.networks:
            try:
                ip = ipaddress.ip_address(address or '')
            except ValueError:
                return 'network'
            if not any(ip in network for network in self.networks):
                return 'network'
        return None

    def allows(self, model_name, operation):
        if operation != 'read' and 'global_readonly' in self.flags:
            return False
        perms = self.perms.get(model_name)
        if perms is None:
            return True
        return perms[OPERATION_INDEX[operation]]

    def model_flag(self, model_name, flag):
        if GLOBAL_FLAG_OF_MODEL_FLAG[flag] in self.flags:
            return True
        return flag in self.model_flags.get(model_name, ())

    def domain_terms(self, model_name, operation):
        """ The domain strings this profile imposes, to be ANDed together. """
        return self.domains.get((model_name, operation), ())

    def field_mode(self, model_name, field_name):
        return self.field_modes.get((model_name, field_name))

    def field_option(self, model_name, field_name, option):
        return option in self.field_options.get((model_name, field_name), ())

    def field_domain(self, model_name, field_name):
        return self.field_domains.get((model_name, field_name))

    def hides_element(self, model_name, element_type, element_name):
        return (model_name, element_type, element_name or '') in self.elements

    def _matching_buttons(self, model_name, button_type, name, view_type=None, button_id=None):
        """ (mode, condition) of the button rules matching. """
        for rule in self.buttons:
            if rule[0] != model_name or rule[2] != button_type or rule[3] != name:
                continue
            if view_type is not None and rule[1] != 'any' and rule[1] != view_type:
                continue
            if button_id is not None and rule[4] and rule[4] != button_id:
                continue
            yield rule[5], rule[6]

    def button_condition(self, modes, model_name, button_type, name, view_type=None, button_id=None):
        """ 'True', 'False' or the condition under which a rule of ``modes`` applies.
        The controllers do not know the view nor the button id: they pass None. """
        return or_conditions([
            condition or 'True'
            for mode, condition in self._matching_buttons(model_name, button_type, name, view_type, button_id)
            if mode in modes
        ])

    def hides_button(self, model_name, view_type, button_type, name, button_id):
        return self.button_condition(HIDE_MODES, model_name, button_type, name, view_type, button_id) == 'True'

    def blocks_button(self, model_name, button_type, name):
        return self.button_condition(BLOCK_MODES, model_name, button_type, name) == 'True'

    def field_condition(self, model_name, field_name, mode):
        """ 'True', 'False' or the condition under which the field is at least in ``mode``. """
        severity = FIELD_MODES.index(mode)
        if FIELD_MODES.index(self.field_mode(model_name, field_name)) >= severity:
            return 'True'
        return or_conditions([
            condition for line_mode, condition in self.field_conditions.get((model_name, field_name), ())
            if FIELD_MODES.index(line_mode) >= severity
        ])

    def page_condition(self, model_name, name):
        if self.hides_element(model_name, 'page', name):
            return 'True'
        return self.element_conditions.get((model_name, 'page', name or ''), 'False')

    def blocks_action(self, action_id):
        """ Whether a rule blocks the action button opening ``action_id``.

        /web/action/load only carries the id, so the rule's model is not matched.
        """
        # loading an action names no record: a rule under a condition cannot be
        # checked there, it only hides the button
        key = str(action_id)
        return any(
            rule[5] in BLOCK_MODES and not rule[6]
            for rule in self.buttons
            if rule[2] == 'action' and rule[3] == key
        )


class AccessRules:
    """ The profiles of one user, and how they combine.

    Additive profiles combine permissively: an operation is allowed as soon as
    one of them allows it, and something is hidden only when all of them hide
    it. Override profiles then subtract, whatever the additive ones said.
    """
    __slots__ = ('additive', 'override', 'view_flags', 'view_models', '_memo')

    def __init__(self, additive=(), override=()):
        self.additive = tuple(additive)
        self.override = tuple(override)
        self._memo = {}
        profiles = self.additive + self.override
        self.view_flags = any(profile.flags & VIEW_FLAGS for profile in profiles)
        self.view_models = frozenset(
            name
            for profile in profiles
            for name in (
                *profile.model_flags,
                *(model for model, _field in profile.field_modes),
                *(model for model, _field in profile.field_conditions),
                *(model for model, _field in profile.field_options),
                *(model for model, _field in profile.field_domains),
                *(rule[0] for rule in profile.buttons),
                *(element[0] for element in profile.elements),
                *(element[0] for element in profile.element_conditions),
            )
        )

    @property
    def enabled(self):
        return bool(self.additive or self.override)

    def _hidden(self, predicate):
        if any(predicate(profile) for profile in self.override):
            return True
        return bool(self.additive) and all(predicate(profile) for profile in self.additive)

    def _combined_condition(self, condition_of):
        """ True, None or the combined condition of a rule: every override
        profile applies it, the additive ones only when all of them do. """
        conditions = [condition_of(profile) for profile in self.override]
        if self.additive:
            conditions.append(and_conditions([condition_of(profile) for profile in self.additive]))
        combined = or_conditions(conditions)
        return True if combined == 'True' else None if combined == 'False' else combined

    def field_condition(self, model_name, field_name, mode):
        return self._combined_condition(lambda profile: profile.field_condition(model_name, field_name, mode))

    def conditional_fields(self, model_name, modes=('hide', 'readonly', 'required')):
        """ {field: condition} of the fields that are in one of ``modes`` only under a
        condition (the strongest mode wins: hidden, then read only, then required). """
        key = ('conditional', model_name, modes)
        if key not in self._memo:
            result = {}
            names = {field for profile in self.additive + self.override
                     for model, field in profile.field_conditions if model == model_name}
            for name in names:
                for mode in modes:
                    condition = self.field_condition(model_name, name, mode)
                    if isinstance(condition, str):
                        result[name] = condition
                        break
                    if condition is True:
                        break
            self._memo[key] = result
        return self._memo[key]

    def button_condition(self, modes, model_name, button_type, name, view_type=None, button_id=None):
        return self._combined_condition(
            lambda profile: profile.button_condition(modes, model_name, button_type, name, view_type, button_id))

    def page_condition(self, model_name, name):
        return self._combined_condition(lambda profile: profile.page_condition(model_name, name))

    def allows(self, model_name, operation):
        if not all(profile.allows(model_name, operation) for profile in self.override):
            return False
        return not self.additive or any(
            profile.allows(model_name, operation) for profile in self.additive
        )

    def record_domains(self, model_name, operation):
        """ Return ``(or_groups, and_groups)`` for one operation.

        Each group is a tuple of domain strings to AND together, being the
        general filter of a profile and its filter for this very operation.
        ``or_groups`` is None when the additive profiles leave the model
        unfiltered, which happens as soon as one of them says nothing about it.
        """
        and_groups = tuple(
            terms
            for profile in self.override
            if (terms := profile.domain_terms(model_name, operation))
        )
        or_groups = []
        for profile in self.additive:
            # a profile that refuses the operation grants no record of it: it
            # must not widen the union to every record
            if not profile.allows(model_name, operation):
                continue
            terms = profile.domain_terms(model_name, operation)
            if not terms:
                return None, and_groups
            or_groups.append(terms)
        return (tuple(or_groups) or None), and_groups

    def menu_blacklist(self):
        hidden = set()
        if self.additive:
            hidden = set(self.additive[0].menus)
            for profile in self.additive[1:]:
                hidden &= profile.menus
        for profile in self.override:
            hidden |= profile.menus
        return hidden

    def model_flags_set(self):
        """ Whether any profile hides a whole Print or Action menu, anywhere. """
        return any(
            'hide_print_all' in profile.flags or 'hide_action_menu_all' in profile.flags
            or any({'hide_print', 'hide_action_menu'} & flags for flags in profile.model_flags.values())
            for profile in self.additive + self.override
        )

    def login_refusal(self, now, address):
        """ Why the profiles refuse a sign-in, or None: every override profile
        must allow it, and one additive profile is enough. """
        for profile in self.override:
            if reason := profile.login_refusal(now, address):
                return reason
        reasons = [profile.login_refusal(now, address) for profile in self.additive]
        if reasons and all(reasons):
            return reasons[0]
        return None

    def home_action(self):
        """ The home page a profile sets: an override profile first, then the
        first additive one, in the order of the profiles. """
        return next((profile.home_action for profile in self.override + self.additive
                     if profile.home_action), None)

    def has_flag(self, flag):
        return self._hidden(lambda profile: flag in profile.flags)

    def model_flag(self, model_name, flag):
        return self._hidden(lambda profile: profile.model_flag(model_name, flag))

    def hides_report(self, action_id):
        return self._hidden(lambda profile: action_id in profile.reports)

    def hides_action(self, action_id):
        return self._hidden(lambda profile: action_id in profile.actions)

    def hides_button(self, model_name, view_type, button_type, name, button_id):
        return self._hidden(
            lambda profile: profile.hides_button(model_name, view_type, button_type, name, button_id)
        )

    def blocks_button(self, model_name, button_type, name):
        return self._hidden(
            lambda profile: profile.blocks_button(model_name, button_type, name)
        )

    def blocks_action(self, action_id):
        return self._hidden(lambda profile: profile.blocks_action(action_id))

    def field_mode(self, model_name, field_name):
        severity = max(
            (FIELD_MODES.index(profile.field_mode(model_name, field_name))
             for profile in self.override),
            default=0,
        )
        if self.additive:
            severity = max(severity, min(
                FIELD_MODES.index(profile.field_mode(model_name, field_name))
                for profile in self.additive
            ))
        return FIELD_MODES[severity]

    def affects_views(self):
        """ Whether any profile says anything at all about views.

        Not narrowed to one model: x2many sub views carry comodel fields.
        """
        return self.view_flags or bool(self.view_models)

    def field_option(self, model_name, field_name, option):
        return self._hidden(
            lambda profile: profile.field_option(model_name, field_name, option))

    def field_domain(self, model_name, field_name):
        """ The value filter of a field, combined like the rest: one additive
        profile's filter is enough (OR), and none when an additive profile sets
        none; every override profile's filter applies (AND). """
        additive = None
        if self.additive:
            terms = [profile.field_domain(model_name, field_name) for profile in self.additive]
            if all(terms):
                additive = or_domains(terms)
        return and_domains([
            *(profile.field_domain(model_name, field_name) for profile in self.override),
            additive,
        ])

    def has_value_filters(self):
        return any(profile.field_domains for profile in self.additive + self.override)

    def hides_element(self, model_name, element_type, element_name=''):
        return self._hidden(
            lambda profile: profile.hides_element(model_name, element_type, element_name))

    def hidden_view_types(self, model_name):
        types = {
            name
            for profile in self.additive + self.override
            for model, element_type, name in profile.elements
            if model == model_name and element_type == 'view'
        }
        return {name for name in types if self.hides_element(model_name, 'view', name)}

    def fields_in_modes(self, model_name, modes):
        """ The fields of a model whose combined mode is one of ``modes``,
        memoised: the field guard asks for every row and every path. """
        key = (model_name, modes)
        memo = self._memo
        if key not in memo:
            memo[key] = frozenset(
                name for name in self.restricted_fields(model_name)
                if self.field_mode(model_name, name) in modes)
        return memo[key]

    def restricts_fields(self):
        """ Whether any profile hides a field, makes one read only or keeps one
        out of the exports. """
        return any(
            mode in ('hide', 'readonly')
            for profile in self.additive + self.override
            for mode in (*profile.field_modes.values(),
                         *(line_mode for lines in profile.field_conditions.values() for line_mode, _c in lines))
        ) or any(
            'no_export' in options
            for profile in self.additive + self.override
            for options in profile.field_options.values()
        )

    def not_exported(self, model_name):
        """ The fields of a model kept out of the exports. """
        names = {
            field_name
            for profile in self.additive + self.override
            for (model, field_name), options in profile.field_options.items()
            if model == model_name and 'no_export' in options
        }
        return {name for name in names if self.field_option(model_name, name, 'no_export')}

    def body_classes(self):
        return [css for flag, css in BODY_CLASSES.items() if self.has_flag(flag)]

    def restricted_fields(self, model_name):
        """ The field names this model has a rule for, whichever profile set it. """
        return {
            field_name
            for profile in self.additive + self.override
            for model, field_name in (*profile.field_modes, *profile.field_conditions)
            if model == model_name
        }


NO_RULES = AccessRules()


class OmAccessProfile(models.Model):
    _name = 'om.access.profile'
    _inherit = ['mail.thread']
    _description = 'Access Profile'
    _order = 'sequence, name, id'

    # every write clears the ormcaches this module and the menus rely on
    _clear_cache_name = 'default'

    name = fields.Char(required=True, translate=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10)
    note = fields.Html(string='Notes')
    company_id = fields.Many2one(
        'res.company', string='Restrict to Company',
        help="Left empty, the profile applies to all of its users. Set, it only "
             "applies to the users who have this company among theirs. It "
             "follows the companies a user belongs to, not the company they are "
             "currently working in.", tracking=True)

    strictness = fields.Selection(
        [('additive', 'Additive'), ('override', 'Override')],
        default='additive', required=True,
        help="Additive profiles combine permissively with the other additive "
             "profiles of the user: an operation is allowed as soon as one of "
             "them allows it. An override profile always applies and can never "
             "be overruled, which is what you want for a blanket such as "
             "'Read Only' stacked on top of another profile.", tracking=True)

    group_id = fields.Many2one(
        'res.groups', string='Technical Group', ondelete='restrict', copy=False,
        help="Created and maintained automatically. It exists so that the group "
             "set of a user stays a unique key for the caches of the menus.")
    user_ids = fields.Many2many(
        'res.users', 'om_access_profile_users_rel', 'profile_id', 'uid',
        string='Users', tracking=True)
    apply_to_admin = fields.Boolean(
        string='Apply to Settings Users',
        help="By default a member of the Settings group is never restricted by "
             "this profile. The Odoo superuser and the Administrator user are "
             "always exempt, whatever this setting says.", tracking=True)

    global_readonly = fields.Boolean(string='Read Only Everywhere', tracking=True)
    hide_chatter_all = fields.Boolean(string='Hide the Chatter Everywhere', tracking=True)
    block_export = fields.Boolean(string='Block Export', tracking=True)
    block_import = fields.Boolean(string='Block Import', tracking=True)
    block_archive = fields.Boolean(string='Block Archiving', tracking=True)
    block_duplicate = fields.Boolean(string='Block Duplication', tracking=True)
    hide_activities = fields.Boolean(string='Hide Activities', tracking=True)
    hide_settings_menu = fields.Boolean(string='Hide the Settings App', tracking=True)
    lock_statusbar = fields.Boolean(string='Lock the Status Bars', tracking=True)
    block_rpc = fields.Boolean(
        string='Block the External API',
        help="Refuses XML-RPC and JSON-RPC logins for these users. They can "
             "still use Odoo in a browser; scripts and integrations signing in "
             "as them cannot.", tracking=True)
    for_new_users = fields.Boolean(
        string='Give to New Users',
        help="Every internal user created from now on gets this profile. Portal "
             "and public users never do.", tracking=True)
    hide_print_all = fields.Boolean(
        string='Hide the Print Menu',
        help="No report can be printed, from the Print menu or from a button.", tracking=True)
    hide_action_menu_all = fields.Boolean(
        string='Hide the Action Menu Entries',
        help="The entries of the Action menu (Send by Email, server actions...) are hidden "
             "and refused. Export, Duplicate, Archive and Delete have their own switches.", tracking=True)
    hide_send_message_all = fields.Boolean(
        string='Hide Send Message',
        help="In the chatter, only Log note remains: messages to the followers and the "
             "customers cannot be sent from it.", tracking=True)
    hide_followers_all = fields.Boolean(string='Hide the Followers', tracking=True)
    hide_attachments_all = fields.Boolean(string='Hide the Attachments', tracking=True)
    home_action_id = fields.Many2one(
        'ir.actions.act_window', string='Home Page',
        help="Where the users of this profile land after signing in, instead of the home "
             "screen or of their own home action.", tracking=True)
    hide_costs = fields.Boolean(
        string='Hide Costs and Margins',
        help="Hides the cost of the products, the margins of the sales and of the point of "
             "sale, and the stock valuation, from the screens and from the API, in every "
             "app installed now or later.", tracking=True)
    hide_sale_prices = fields.Boolean(
        string='Hide Sales Prices',
        help="Hides the sales price of the products and the prices, discounts and amounts of "
             "the quotations and sales orders. For people who handle the goods, not the deals.", tracking=True)
    block_login = fields.Boolean(
        string='Block Login',
        help="Refuses every sign-in of these users, in the browser and through "
             "the external API, and ends the sessions they have open. Their "
             "records stay untouched: take them out of the profile to let them "
             "back in, e.g. at the end of a leave.", tracking=True)
    block_developer_mode = fields.Boolean(
        string='Block Developer Mode',
        help="Clears the debug flag on every request, so these users cannot "
             "turn the developer tools on, by the menu or by the URL.", tracking=True)
    block_custom_filter = fields.Boolean(
        string='No Custom Filters',
        help="Hides 'Custom Filter...' and 'Custom Date...' in the search bar: only "
             "the filters of the screens remain.", tracking=True)
    block_custom_group = fields.Boolean(
        string='No Custom Group By',
        help="Hides 'Add Custom Group' in the search bar.", tracking=True)
    block_favorites = fields.Boolean(
        string='No Saved Searches',
        help="Hides 'Save current search' and refuses saving a favorite.", tracking=True)
    block_properties = fields.Boolean(
        string='No New Properties',
        help="Hides 'Add Property' and refuses changing the properties of any form.",
        tracking=True)
    block_apps = fields.Boolean(
        string='Block Installing Apps',
        help="Refuses installing, upgrading and uninstalling modules. Meaningful for "
             "Settings users, with 'Apply to Settings Users'.", tracking=True)

    granted_group_ids = fields.Many2many(
        'res.groups', 'om_access_profile_granted_group_rel', 'profile_id', 'group_id',
        string='Granted Access',
        help="Odoo groups the users of this profile get, on top of their own: open "
             "an app (Purchase / User) to users whose form leaves it empty. Taken "
             "away with the profile.", tracking=True)
    hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_access_profile_menu_rel', 'profile_id', 'menu_id',
        string='Hidden Menus',
        help="The children of a hidden menu are hidden with it.", tracking=True)
    hidden_report_ids = fields.Many2many(
        'ir.actions.report', 'om_access_profile_report_rel', 'profile_id', 'report_id',
        string='Hidden Reports', tracking=True)
    # Action menu entries are server or window actions: two tables, hence two
    # fields; the checks match on the shared action id.
    hidden_action_ids = fields.Many2many(
        'ir.actions.server', 'om_access_profile_server_action_rel', 'profile_id', 'action_id',
        string='Hidden Server Actions', tracking=True)
    hidden_window_action_ids = fields.Many2many(
        'ir.actions.act_window', 'om_access_profile_window_action_rel', 'profile_id', 'action_id',
        string='Hidden Window Actions', domain=[('binding_model_id', '!=', False)], tracking=True)

    model_ids = fields.One2many('om.access.profile.model', 'profile_id', string='Models')
    menu_rule_ids = fields.One2many(
        'om.access.profile.menu', 'profile_id', string='Menu Rules',
        help="Rights set on a menu, for the data of its whole branch.")
    allowed_ids = fields.One2many('om.access.allowed', 'profile_id', string='Allowed Records')
    field_ids = fields.One2many('om.access.profile.field', 'profile_id', string='Fields')
    button_ids = fields.One2many('om.access.profile.button', 'profile_id', string='Buttons')
    element_ids = fields.One2many(
        'om.access.profile.element', 'profile_id', string='View Elements')
    # the same lines, one tab each
    page_element_ids = fields.One2many(
        'om.access.profile.element', 'profile_id', string='Pages',
        domain=[('element_type', '=', 'page')])
    filter_element_ids = fields.One2many(
        'om.access.profile.element', 'profile_id', string='Filters',
        domain=[('element_type', 'in', ('filter', 'searchpanel'))])
    view_element_ids = fields.One2many(
        'om.access.profile.element', 'profile_id', string='Views',
        domain=[('element_type', '=', 'view')])

    user_count = fields.Integer(compute='_compute_user_count', string='# Users')

    @api.depends('user_ids', 'group_ids', 'assignment_ids.state')
    def _compute_user_count(self):
        for profile in self:
            profile.user_count = len(profile._om_members())

    #
    # the technical group
    #

    def _group_values(self):
        self.ensure_one()
        return {
            'name': _('Access Profile: %s', self.name),
            'users': [(6, 0, self._om_direct_users().ids)],
            # what the profile grants comes with its group; an archived group
            # still implies its groups, so an archived profile grants nothing
            'implied_ids': [(6, 0, self.granted_group_ids.ids if self.active else [])],
            'comment': _("Maintained by the access profile of the same name. "
                         "Do not assign it by hand."),
        }

    def _sync_group(self):
        """ Keep one hidden res.groups per profile, carrying the same users.

        It makes a user's group set a unique key for _visible_menu_ids(),
        which is cached per group set and not per user.
        """
        self._om_record_grants()
        for profile in self:
            if profile.group_id:
                profile.group_id.sudo().write(profile._group_values())
            else:
                group = self.env['res.groups'].sudo().create(profile._group_values())
                profile.with_context(om_access_skip_sync=True).group_id = group
        self._om_revoke_grants()

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles._sync_group()
        return profiles

    def write(self, vals):
        result = super().write(vals)
        # rewriting the group clears the access caches of every worker: only
        # when what the group carries changes, not for a note or a switch
        if not self.env.context.get('om_access_skip_sync') and GROUP_FIELDS.intersection(vals):
            self._sync_group()
        return result

    def unlink(self):
        self._om_revoke_grants(everything=True)
        groups = self.group_id.sudo()
        result = super().unlink()
        groups.unlink()
        return result

    def copy_data(self, default=None):
        default = dict(default or {})
        default.setdefault('group_id', False)
        default.setdefault('user_ids', [])
        vals_list = super().copy_data(default=default)
        for profile, vals in zip(self, vals_list):
            vals.setdefault('name', _('%s (copy)', profile.name))
        return vals_list

    @api.constrains('granted_group_ids')
    def _check_granted_groups(self):
        forbidden = self.env['res.groups']
        for xmlid in UNGRANTABLE_GROUPS:
            forbidden |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.groups']
        for profile in self:
            for group in profile.sudo().granted_group_ids:
                if (group | group.trans_implied_ids) & forbidden:
                    raise ValidationError(_(
                        "A profile cannot grant %s: it would make its users administrators, "
                        "or access managers. Give it on the user form instead.", group.full_name))
                if group.id in profile.sudo().group_id.ids:
                    raise ValidationError(_("A profile cannot grant its own group."))

    @api.constrains('hide_settings_menu', 'block_login', 'login_slot_ids', 'allowed_ips',
                    'user_ids', 'group_ids', 'apply_to_admin', 'active', 'hidden_menu_ids')
    def _check_last_administrator(self):
        """ Refuse a change leaving no access manager able to undo it: every one
        locked out of signing in, of the Access Manager app or of the access
        profiles, by all their profiles combined. """
        managers_group = self.env.ref('om_access_manager.group_access_manager', raise_if_not_found=False)
        if not managers_group or not self:
            return
        # the rules as they are now, not as cached before this change
        self.env.registry.clear_caches()
        managers = managers_group.sudo().users.filtered('active')
        # no active access manager left at all is the worst lock out
        reasons = [self._om_lockout(manager) for manager in managers] or ['login']
        if all(reasons):
            names = ', '.join(self.mapped('name')[:3]) + (', ...' if len(self) > 3 else '')
            if reasons[0] == 'login':
                raise ValidationError(_(
                    "Profile %s would block the login of every user who "
                    "could undo it. Leave at least one access manager (Access "
                    "Management group) out of it.", names))
            if reasons[0] == 'app':
                raise ValidationError(_(
                    "Profile %s would hide the Access Manager app from every user who "
                    "could put it back. Leave at least one access manager (Access "
                    "Management group) out of it.", names))
            raise ValidationError(_(
                "Profile %s would take the access profiles away from every user who "
                "could give them back. Leave at least one access manager (Access "
                "Management group) out of it.", names))

    @api.model
    def _om_lockout(self, user):
        """ Why ``user`` could not undo a profile, all their profiles combined:
        'login', 'app' or 'profiles'; False when they could. """
        if user.id in self._exempt_user_ids():
            return False
        rules = self._resolve(user.id)
        if not rules.enabled:
            return False
        if rules.has_flag('block_login'):
            return 'login'
        # working hours and networks: refused at some moment or from some place
        limits = [bool(profile.login_slots or profile.networks) for profile in rules.override]
        if any(limits) or (rules.additive and all(
                profile.login_slots or profile.networks for profile in rules.additive)):
            return 'login'
        app = self.env.ref('om_access_manager.om_access_root_menu', raise_if_not_found=False)
        if app and app.id in rules.menu_blacklist():
            return 'app'
        if not (rules.allows(self._name, 'read') and rules.allows(self._name, 'write')):
            return 'profiles'
        return False
        rules = self._resolve(user.id)
        if not rules.enabled:
            return False
        if rules.has_flag('block_login'):
            return 'login'
        # working hours and networks: refused at some moment or from some place
        limits = [bool(profile.login_slots or profile.networks) for profile in rules.override]
        if any(limits) or (rules.additive and all(
                profile.login_slots or profile.networks for profile in rules.additive)):
            return 'login'
        settings_menu = self.env.ref('base.menu_administration', raise_if_not_found=False)
        if rules.has_flag('hide_settings_menu') or (settings_menu and settings_menu.id in rules.menu_blacklist()):
            return 'settings'
        if not (rules.allows(self._name, 'read') and rules.allows(self._name, 'write')):
            return 'profiles'
        return False

    #
    # actions of the single screen
    #

    def action_open_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Users'),
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self._om_members().ids)],
        }

    def _open_wizard(self, res_model, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': res_model,
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_id': self.id,
                        'default_profile_id': self.id},
        }

    @api.model
    @tools.ormcache()
    def _om_user_fields_in_filters(self):
        """ The fields of the user the record filters read (``user.employee_id``):
        a change of one of them must reach the cached filters. """
        names = set()
        lines = self.env['om.access.profile.model'].sudo().search([])
        for line in lines:
            for field_name in DOMAIN_FIELDS:
                names.update(re.findall(r'\buser\.(\w+)', line[field_name] or ''))
        return frozenset(names)

    @api.model
    def _om_eval_context(self):
        """ The record filter eval context: a standard access domain's, plus uid. """
        return dict(self.env['ir.rule']._eval_context(), uid=self.env.uid, time=safe_eval_time,
                    datetime=safe_eval_datetime, relativedelta=relativedelta,
                    context_today=lambda: fields.Date.context_today(self))

    def action_load_models(self):
        return self._open_wizard('om.access.load.models', _('Load Models'))

    def action_restrict_app(self):
        return self._open_wizard('om.access.app.wizard', _('Restrict an App'))

    def action_scan_buttons(self):
        return self._open_wizard('om.access.scan.buttons', _('Scan Buttons'))

    def _om_preview_users(self):
        """ The members of the profile the current user may preview. """
        self.ensure_one()
        viewer = self.env.user.sudo()
        return self._om_members().filtered(lambda user: not user._om_preview_refusal(viewer))

    def action_test_user(self):
        self.ensure_one()
        users = self._om_preview_users()
        if not users:
            raise UserError(_(
                "No user has this profile yet.\n\n"
                "Add users to the profile (Users), save, then preview it as one of them."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preview as User'),
            'res_model': 'om.access.test.user',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_id': self.id,
                'default_user_id': users[:1].id,
                'om_preview_back': f'/web#action=om_access_manager.om_access_profile_action&id={self.id}&view_type=form',
            },
        }

    def action_copy_restrictions(self):
        return self._open_wizard('om.access.copy.restrictions', _('Copy Restrictions'))

    #
    # resolution
    #

    @api.model
    def _exempt_user_ids(self):
        data = self.env['ir.model.data'].sudo()
        ids = (data._xmlid_to_res_id(xmlid, raise_if_not_found=False)
               for xmlid in EXEMPT_USER_XMLIDS)
        return tuple(user_id for user_id in ids if user_id)

    def _allowed_filters(self, user=None):
        """ {model: domain} of the allowed records of this profile for ``user``. """
        self.ensure_one()
        allowed, per_user = {}, set()
        for line in self.allowed_ids:
            if line.kind not in ALLOWED_KINDS:
                continue
            ids = allowed.setdefault(line.kind, set())
            if line.per_user:
                per_user.add(line.kind)
            elif line.res_id:
                ids.add(line.res_id)
        if user and per_user:
            for line in user.sudo().access_allowed_ids:
                if line.kind in per_user and line.res_id:
                    allowed[line.kind].add(line.res_id)
        filters = {}
        Allowed = self.env['om.access.allowed']
        for kind, ids in allowed.items():
            for model_name, domain in Allowed._filters(kind, ids).items():
                filters[model_name] = (
                    "['&'] + %s + %s" % (filters[model_name], domain) if model_name in filters else domain)
        return filters

    def _build_rules(self, user=None):
        """ Freeze this profile into a ProfileRules, free of any recordset.

        ``user`` is the user the rules are built for: the allowed records ticked
        "each user's own" are read from their form.
        """
        self.ensure_one()
        profile = self.sudo()

        flags = frozenset(flag for flag in GLOBAL_FLAGS if profile[flag])

        perms, domains, model_flags = {}, {}, {}
        for line in profile.model_ids:
            model_name = line.model_id.model
            if not model_name:
                continue
            perms[model_name] = tuple(bool(line[fname]) for fname in PERM_FIELDS)
            general = (line.domain or '').strip()
            for operation in OPERATIONS:
                specific = (line[DOMAIN_FIELD_OF_OPERATION[operation]] or '').strip()
                terms = tuple(term for term in (general, specific) if term)
                if terms:
                    domains[(model_name, operation)] = terms
            present = frozenset(flag for flag in MODEL_FLAGS if line[flag])
            if present:
                model_flags[model_name] = present

        # rights set on menus, for the data without a line of its own
        sources = {}
        for model_name, (rights, by_operation, present, menus) in profile.menu_rule_ids._om_rights_by_model().items():
            if model_name in perms:
                continue
            sources[model_name] = menus
            perms[model_name] = rights
            for operation, terms in by_operation.items():
                domains[(model_name, operation)] = terms
            if present:
                model_flags[model_name] = present

        # the allowed records: one more filter on every model of their kind
        for model_name, domain in profile._allowed_filters(user).items():
            for operation in OPERATIONS:
                domains[(model_name, operation)] = domains.get((model_name, operation), ()) + (domain,)

        field_modes, field_options, field_domains, field_conditions = {}, {}, {}, {}
        for line in profile.field_ids:
            model_name, field_name = line.model_id.model, line.field_id.name
            if not (model_name and field_name):
                continue
            key = (model_name, field_name)
            condition = (line.condition or '').strip()
            if line.mode != 'keep' and condition:
                field_conditions[key] = field_conditions.get(key, ()) + ((line.mode, condition),)
            elif line.mode != 'keep':
                field_modes[key] = line.mode
            options = frozenset(option for option in FIELD_OPTIONS if line[option])
            if options:
                field_options[key] = options
            if (line.field_domain or '').strip():
                field_domains[key] = line.field_domain.strip()
        for switch, switch_fields in FIELD_SWITCHES:
            if not profile[switch]:
                continue
            for model_name, field_name in switch_fields:
                if model_name in self.env and field_name in self.env[model_name]._fields:
                    key = (model_name, field_name)
                    if FIELD_MODES.index(field_modes.get(key)) < FIELD_MODES.index('hide'):
                        field_modes[key] = 'hide'

        elements = frozenset(
            (line.model_id.model, line.element_type, line.element_name or '')
            for line in profile.element_ids
            if line.model_id.model and not (line.condition or '').strip()
        )
        element_conditions = {
            (line.model_id.model, line.element_type, line.element_name or ''): line.condition.strip()
            for line in profile.element_ids
            if line.model_id.model and (line.condition or '').strip()
        }

        buttons = tuple(
            (line.model_id.model, line.view_type, line.button_type,
             line.button_name, line.button_id or '', line.mode, (line.condition or '').strip())
            for line in profile.button_ids
            if line.model_id.model and line.button_name
        )

        menus = frozenset()
        if profile.hidden_menu_ids:
            menus = frozenset(self.env['ir.ui.menu'].sudo().with_context(**{'ir.ui.menu.full_list': True}).with_context(active_test=False).search(
                [('id', 'child_of', profile.hidden_menu_ids.ids)]
            )._ids)

        return ProfileRules(
            id=profile.id,
            name=profile.name,
            flags=flags,
            perms=frozendict(perms),
            domains=frozendict(domains),
            menus=menus,
            buttons=buttons,
            field_modes=frozendict(field_modes),
            field_options=frozendict(field_options),
            field_domains=frozendict(field_domains),
            elements=elements,
            reports=frozenset(profile.hidden_report_ids._ids),
            actions=frozenset(profile.hidden_action_ids._ids + profile.hidden_window_action_ids._ids),
            model_flags=frozendict(model_flags),
            home_action=profile.home_action_id.id or None,
            login_slots=tuple(
                (int(slot.dayofweek), slot.hour_from, slot.hour_to) for slot in profile.login_slot_ids),
            login_tz=profile.login_tz or 'UTC',
            networks=parse_networks(profile.allowed_ips),
            field_conditions=frozendict(field_conditions),
            element_conditions=frozendict(element_conditions),
            sources=frozendict(sources),
        )

    @api.model
    @tools.ormcache('uid')
    def _resolve(self, uid):
        """ The profiles that apply to ``uid``, frozen and cached per user. """
        if uid in self._exempt_user_ids():
            return NO_RULES
        user = self.env['res.users'].sudo().browse(uid)
        if not user.exists():
            return NO_RULES
        profiles = self._om_profiles_of(user).filtered('active')
        if profiles:
            # Follows the user's companies, not the company switcher: core
            # caches menus per user without the company in the key.
            companies = set(user.company_ids._ids)
            profiles = profiles.filtered(
                lambda profile: not profile.company_id or profile.company_id.id in companies)
        if profiles and user.has_group('base.group_system'):
            profiles = profiles.filtered('apply_to_admin')
        if not profiles:
            return NO_RULES
        return AccessRules(
            additive=[p._build_rules(user) for p in profiles if p.strictness == 'additive'],
            override=[p._build_rules(user) for p in profiles if p.strictness == 'override'],
        )

    @api.model
    def _current_rules(self):
        """ The rules of the current user, or NO_RULES when nothing applies. """
        if self.env.su:
            return NO_RULES
        return self._resolve(self.env.uid)

    #
    # checks called from the controllers
    #

    @api.model
    def _om_refusal(self, message, **values):
        """ The error refusing an operation, logged in the audit log first (the
        line survives the rollback the error causes). """
        self.env['om.user.audit.log']._om_log('refused', separate=True, detail=message, **values)
        return AccessError(message)

    def _check_button(self, model_name, button_type, name, ids=None):
        """ Refuse a blocked button; one blocked under a condition only on the
        records ``ids`` matching it. """
        rules = self._current_rules()
        if not rules.enabled:
            return
        condition = rules.button_condition(BLOCK_MODES, model_name, button_type, name)
        if condition is None:
            return
        if condition is not True and not (
                ids and model_name in self.env and self.env[model_name]._om_matching(condition, ids)):
            return
        raise self._om_refusal(_(
            "You are not allowed to use this button.\n\n"
            "Your access profile blocks '%(button)s' on '%(model)s'.",
            button=name, model=model_name), model=model_name, method=name, record_ids=ids or [])

    @api.model
    def _check_action(self, action_id):
        rules = self._current_rules()
        if not rules.enabled or not action_id:
            return
        if (rules.hides_report(action_id)
                or rules.hides_action(action_id)
                or rules.blocks_action(action_id)
                or self._hides_menu_of(rules, action_id)):
            action = self.env['ir.actions.actions'].sudo().browse(action_id).exists()
            raise self._om_refusal(_(
                "You are not allowed to run this action.\n\n"
                "Your access profile hides it."), method=action.name or str(action_id))

    @api.model
    def _hides_menu_of(self, rules, action_id):
        """ Whether the action belongs to a Print or Action menu a profile hides
        whole: a report of the model, or an entry bound to its Action menu. """
        if not rules.model_flags_set():
            return False
        self.env.cr.execute(
            "SELECT a.type, a.binding_type, m.model FROM ir_actions a "
            "LEFT JOIN ir_model m ON m.id = a.binding_model_id WHERE a.id = %s", [action_id])
        row = self.env.cr.fetchone()
        if not row:
            return False
        action_type, binding_type, binding_model = row
        if action_type == 'ir.actions.report':
            report_model = self.env['ir.actions.report'].sudo().browse(action_id).model
            return rules.model_flag(report_model, 'hide_print')
        return bool(binding_model and binding_type == 'action'
                    and rules.model_flag(binding_model, 'hide_action_menu'))

    @api.model
    def _filter_action_views(self, action):
        """ Drop the view types a profile hides from a window action.

        The last remaining view type is always kept: an action with nothing to
        render is worse than one view too many.
        """
        if not isinstance(action, dict) or action.get('type') != 'ir.actions.act_window':
            return action
        model_name = action.get('res_model')
        if not model_name:
            return action
        rules = self._current_rules()
        if not rules.enabled:
            return action
        hidden = rules.hidden_view_types(model_name)
        if not hidden:
            return action

        views = [view for view in action.get('views') or [] if view[1] not in hidden]
        if not views:
            return action
        action['views'] = views
        action['view_mode'] = ','.join(view[1] for view in views)
        if action.get('view_type') in hidden:
            action['view_type'] = views[0][1]
        return action

    #
    # view rewriting, called from Base._get_view()
    #

    @staticmethod
    def _set_option(node, key, value):
        raw = node.get('options') or '{}'
        try:
            options = json.loads(raw)
        except ValueError:
            try:
                options = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                options = {}
        if not isinstance(options, dict):
            options = {}
        options[key] = value
        node.set('options', json.dumps(options))

    @api.model
    def _om_field_own_domain(self, model_name, field_name):
        """ The domain of the field itself, which a domain set on the view
        replaces in the web client. """
        field = self.env[model_name]._fields.get(field_name) if model_name in self.env else None
        domain = getattr(field, 'domain', None)
        if isinstance(domain, (list, tuple)):
            return repr(list(domain))
        return domain if isinstance(domain, str) else None

    @staticmethod
    def _merge_domain(existing, extra):
        """ AND a value filter into the domain a field node already carries. """
        return and_domains([existing, extra])

    def _apply_field_conditions(self, rules, node, model_name, field_name, view_type, needed):
        """ The rules of a field that apply only under a condition. """
        condition = rules.field_condition(model_name, field_name, 'hide')
        if isinstance(condition, str):
            self._add_condition(node, 'invisible', condition, model_name, view_type, needed)
            self._add_condition(node, 'readonly', condition, model_name, view_type, needed)
            return
        for mode, attribute in (('readonly', 'readonly'), ('required', 'required')):
            condition = rules.field_condition(model_name, field_name, mode)
            if isinstance(condition, str):
                self._add_condition(node, attribute, condition, model_name, view_type, needed)

    def _add_condition(self, node, attribute, condition, model_name, view_type, needed):
        """ OR a profile's condition into an attribute of the view: a domain
        of its attrs on Odoo 16, where the view conditions are domains. """
        existing = (node.get(attribute) or '').strip()
        if existing in ('1', 'True', 'true'):
            return
        try:
            attrs = ast.literal_eval((node.get('attrs') or '{}').strip()) or {}
        except (ValueError, SyntaxError):
            return
        current = attrs.get(attribute)
        if current is True or (isinstance(current, int) and current):
            return
        current = list(current) if isinstance(current, (list, tuple)) else []
        if attribute == 'invisible' and node.get('states'):
            # as Odoo 16 reads them: the states with the domain of attrs, implicitly ANDed
            current.append(('state', 'not in', node.attrib.pop('states').split(',')))
        domain = condition_domain(condition, self.env[model_name], self.env.uid)
        attrs[attribute] = expression.OR([expression.normalize_domain(current), domain]) if current else domain
        node.set('attrs', repr(attrs))
        root = next((ancestor for ancestor in node.iterancestors() if ancestor.tag in VIEW_ROOTS), None)
        if root is not None:
            needed.setdefault(root, (model_name, set()))[1].update(condition_fields(condition))

    def _add_needed_names(self, node, model_name, names, needed):
        """ Have the view load the fields of the record an expression reads. """
        root = next((ancestor for ancestor in node.iterancestors() if ancestor.tag in VIEW_ROOTS), None)
        names = names & set(self.env[model_name]._fields) if model_name in self.env else set()
        if root is not None and names:
            needed.setdefault(root, (model_name, set()))[1].update(names)

    @classmethod
    def _add_needed_fields(cls, needed):
        """ Add, invisible, the fields a condition reads and its view lacks. """
        for root, (model_name, names) in needed.items():
            present = {
                field.get('name') for field in root.iter('field')
                if next((a for a in field.iterancestors() if a.tag in VIEW_ROOTS), None) is root
            }
            for name in sorted(names - present):
                # invisible="1" hides a column of a list on Odoo 16
                root.append(etree.Element('field', {'name': name, 'invisible': '1'}))

    @classmethod
    def _hide_field(cls, node, view_type):
        """ Hide a field without removing it, as other parts of the view may
        refer to it; the field guard blanks its value. It is removed only in
        views that search or aggregate on it, where the guard would refuse it.
        """
        container = next(
            (ancestor.tag for ancestor in node.iterancestors() if ancestor.tag in VIEW_ROOTS),
            view_type)
        if container in REMOVED_IN_VIEWS:
            cls._drop(node)
            return
        # invisible="1" hides a column of a list on Odoo 16
        node.set('invisible', '1')
        node.set('readonly', '1')
        for attribute in ('sum', 'avg', 'aggregator', 'required'):
            node.attrib.pop(attribute, None)

    @staticmethod
    def _drop(node):
        """ Remove a node and keep the surrounding text tidy. """
        parent = node.getparent()
        if parent is None:
            return
        tail = node.tail
        previous = node.getprevious()
        parent.remove(node)
        if tail:
            if previous is not None:
                previous.tail = (previous.tail or '') + tail
            else:
                parent.text = (parent.text or '') + tail

    @api.model
    def _comodel(self, model_name, field_name):
        """ The model the children of a <field> node belong to, or None. """
        if not (model_name and field_name):
            return None
        model = self.env.get(model_name)
        field = model._fields.get(field_name) if model is not None else None
        return field.comodel_name if field is not None and field.relational else None

    @api.model
    def _iter_nodes(self, node, model_name):
        """ Yield ``(node, model)`` for the node and all of its descendants,
        the model following the nested views of x2many fields. """
        yield node, model_name
        if node.tag == 'field':
            model_name = self._comodel(model_name, node.get('name'))
        for child in node:
            yield from self._iter_nodes(child, model_name)

    @api.model
    def _apply_view_rules(self, rules, tree, model_name, view_type):
        """ Rewrite the architecture of a view for the current user.

        Cosmetic only: enforcement lives in the access rules (ir.model.access, ir.rule), the field
        guard and the controllers.
        """
        lock_statusbar = rules.has_flag('lock_statusbar')
        hide_activities = rules.has_flag('hide_activities')
        chatter_hidden = {}
        # the fields a condition reads, per view (the root of a view or of the
        # sub-view of an x2many): they must be in it for the client to evaluate it
        needed = {}

        for node, node_model in list(self._iter_nodes(tree, model_name)):
            tag = node.tag

            if tag == 'div' and 'oe_chatter' in (node.get('class') or '').split():
                # the chatter of an Odoo 16 form
                if node_model is None:
                    continue
                if node_model not in chatter_hidden:
                    chatter_hidden[node_model] = rules.model_flag(node_model, 'hide_chatter')
                if chatter_hidden[node_model]:
                    self._drop(node)
                continue

            if tag == 'form' and node_model:
                classes = [css for flag, css in CHATTER_CLASSES if rules.model_flag(node_model, flag)]
                if classes:
                    node.set('class', ' '.join(filter(None, [node.get('class'), *classes])))

            if tag == 'filter' and node_model:
                # the field guard would refuse a filter on a hidden field
                hidden = {name for name in rules.restricted_fields(node_model)
                          if rules.field_mode(node_model, name) == 'hide'}
                hidden |= set(rules.conditional_fields(node_model, ('hide',)))
                text = (node.get('domain') or '') + (node.get('context') or '')
                if hidden and any(re.search(r'''['"]%s[.'"]''' % re.escape(name), text) for name in hidden):
                    self._drop(node)
                    continue

            if tag == 'field':
                field_name = node.get('name')
                if hide_activities and (field_name in ACTIVITY_FIELDS
                                        or node.get('widget') in ACTIVITY_WIDGETS):
                    self._drop(node)
                    continue
                if node_model:
                    mode = rules.field_mode(node_model, field_name)
                    if mode == 'hide':
                        self._hide_field(node, view_type)
                        continue
                    if mode == 'readonly':
                        # no force_save: the field guard drops what is written to it anyway
                        node.set('readonly', '1')
                    elif mode == 'required':
                        node.set('required', '1')
                    self._apply_field_conditions(rules, node, node_model, field_name, view_type, needed)
                    if rules.field_option(node_model, field_name, 'no_open'):
                        self._set_option(node, 'no_open', True)
                    if rules.field_option(node_model, field_name, 'no_create'):
                        self._set_option(node, 'no_create', True)
                        self._set_option(node, 'no_quick_create', True)
                        self._set_option(node, 'no_create_edit', True)
                    value_filter = rules.field_domain(node_model, field_name)
                    if value_filter:
                        merged = self._merge_domain(
                            node.get('domain') or self._om_field_own_domain(node_model, field_name), value_filter)
                        if merged:
                            node.set('domain', merged)
                            self._add_needed_names(node, node_model, names_read(merged), needed)
                if lock_statusbar and node.get('widget') == 'statusbar':
                    self._set_option(node, 'clickable', False)
                continue

            if tag == 'button' and node.get('name') and not node.get('special') and node_model:
                condition = rules.button_condition(
                    HIDE_MODES, node_model, node.get('type') or 'object', node.get('name'), view_type,
                    node.get('id') or '')
                if condition is True:
                    self._drop(node)
                elif condition:
                    self._add_condition(node, 'invisible', condition, node_model, view_type, needed)
                continue

            if tag == 'page' and node_model:
                condition = rules.page_condition(node_model, node.get('name') or '')
                if condition is True:
                    self._drop(node)
                elif condition:
                    self._add_condition(node, 'invisible', condition, node_model, view_type, needed)
                continue

            if tag == 'filter' and node_model:
                # a group by is a <filter> node too, so this covers both
                if rules.hides_element(node_model, 'filter', node.get('name') or ''):
                    self._drop(node)
                continue

            if tag == 'searchpanel' and node_model:
                if rules.hides_element(node_model, 'searchpanel'):
                    self._drop(node)

        self._add_needed_fields(needed)

        if tree.tag in ('form', 'list', 'tree', 'kanban'):
            if rules.model_flag(model_name, 'hide_export'):
                tree.set('export_xlsx', '0')
            if rules.model_flag(model_name, 'hide_import'):
                # base_import reads this to offer the Import menu entry
                tree.set('import', '0')
            if rules.model_flag(model_name, 'hide_duplicate'):
                tree.set('duplicate', '0')
        return tree
