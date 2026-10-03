# Access profile: the single screen the administrator edits, and the resolver
# every enforcement hook of this module reads from.
import ast
import ipaddress
import re
import json
import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import frozendict

from .om_access_allowed import ALLOWED_KINDS
from .login_tools import parse_networks

from .om_access_profile_model import DOMAIN_FIELD_OF_OPERATION

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
    'hide_attachments_all', 'single_session',
)

FIELD_MODES = (None, 'required', 'readonly', 'hide')  # ordered by severity
# what the hidden group of a profile carries (_group_values)
GROUP_FIELDS = frozenset({'name', 'user_ids', 'active', 'company_id'})

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
FIELD_OPTIONS = ('no_open', 'no_create')

ACTIVITY_FIELDS = frozenset({'activity_ids', 'activity_state', 'activity_date_deadline'})
ACTIVITY_WIDGETS = frozenset({'list_activity', 'mail_activity'})

# the global switches that make a view worth rewriting
VIEW_FLAGS = frozenset({
    'hide_chatter_all', 'block_export', 'block_import', 'block_archive',
    'block_duplicate', 'hide_activities', 'lock_statusbar',
    'hide_send_message_all', 'hide_followers_all', 'hide_attachments_all',
})


class ProfileRules:
    """ The rules of one profile, frozen and free of any recordset.

    Instances end up in the ormcache, which outlives the cursor they were built
    with, so nothing here may hold an environment.
    """
    __slots__ = ('id', 'name', 'flags', 'perms', 'domains', 'menus', 'buttons',
                 'field_modes', 'field_options', 'field_domains', 'elements',
                 'reports', 'actions', 'model_flags', 'home_action',
                 'login_slots', 'login_tz', 'networks')

    def __init__(self, id, name, flags, perms, domains, menus, buttons,
                 field_modes, field_options, field_domains, elements,
                 reports, actions, model_flags, home_action=None,
                 login_slots=(), login_tz='UTC', networks=()):
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
        for rule in self.buttons:
            if rule[0] != model_name or rule[2] != button_type or rule[3] != name:
                continue
            if view_type is not None and rule[1] != 'any' and rule[1] != view_type:
                continue
            if button_id is not None and rule[4] and rule[4] != button_id:
                continue
            yield rule[5]

    def hides_button(self, model_name, view_type, button_type, name, button_id):
        return any(
            mode in ('hide', 'hide_block')
            for mode in self._matching_buttons(model_name, button_type, name, view_type, button_id)
        )

    def blocks_button(self, model_name, button_type, name):
        # The controller only knows the model and method, so view_type and
        # button_id are deliberately ignored here.
        return any(
            mode in ('block', 'hide_block')
            for mode in self._matching_buttons(model_name, button_type, name)
        )

    def blocks_action(self, action_id):
        """ Whether a rule blocks the action button opening ``action_id``.

        /web/action/load only carries the id, so the rule's model is not matched.
        """
        key = str(action_id)
        return any(
            rule[5] in ('block', 'hide_block')
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
                *(rule[0] for rule in profile.buttons),
                *(element[0] for element in profile.elements),
            )
        )

    @property
    def enabled(self):
        return bool(self.additive or self.override)

    def _hidden(self, predicate):
        if any(predicate(profile) for profile in self.override):
            return True
        return bool(self.additive) and all(predicate(profile) for profile in self.additive)

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
        """ The AND of every value filter set for this field, whichever profile
        set it: a value filter only narrows a dropdown, it refuses nothing. """
        terms = [
            domain
            for profile in self.additive + self.override
            if (domain := profile.field_domain(model_name, field_name))
        ]
        if not terms:
            return None
        if len(terms) == 1:
            return terms[0]
        # The client's domain evaluator is not full Python: merge only plain
        # literals, else keep the first filter.
        merged = []
        for term in terms:
            try:
                value = ast.literal_eval(term)
            except (ValueError, SyntaxError):
                return terms[0]
            if not isinstance(value, list):
                return terms[0]
            merged.extend(value)
        return repr(merged)

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
        """ Whether any profile hides a field or makes one read only. """
        return any(
            mode in ('hide', 'readonly')
            for profile in self.additive + self.override
            for mode in profile.field_modes.values()
        )

    def restricted_fields(self, model_name):
        """ The field names this model has a rule for, whichever profile set it. """
        return {
            field_name
            for profile in self.additive + self.override
            for model, field_name in profile.field_modes
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
    allowed_ids = fields.One2many('om.access.allowed', 'profile_id', string='Allowed Records')
    field_ids = fields.One2many('om.access.profile.field', 'profile_id', string='Fields')
    button_ids = fields.One2many('om.access.profile.button', 'profile_id', string='Buttons')
    element_ids = fields.One2many(
        'om.access.profile.element', 'profile_id', string='View Elements')

    user_count = fields.Integer(compute='_compute_user_count', string='# Users')

    @api.depends('user_ids')
    def _compute_user_count(self):
        for profile in self:
            profile.user_count = len(profile.user_ids)

    #
    # the technical group
    #

    def _group_values(self):
        self.ensure_one()
        return {
            'name': _('Access Profile: %s', self.name),
            'user_ids': [(6, 0, self.user_ids.ids)],
            'comment': _("Maintained by the access profile of the same name. "
                         "Do not assign it by hand."),
        }

    def _sync_group(self):
        """ Keep one hidden res.groups per profile, carrying the same users.

        It makes a user's group set a unique key for _visible_menu_ids(),
        which is cached per group set and not per user.
        """
        for profile in self:
            if profile.group_id:
                profile.group_id.sudo().write(profile._group_values())
            else:
                group = self.env['res.groups'].sudo().create(profile._group_values())
                profile.with_context(om_access_skip_sync=True).group_id = group

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

    @api.constrains('hide_settings_menu', 'block_login', 'login_slot_ids', 'allowed_ips',
                    'user_ids', 'apply_to_admin', 'active')
    def _check_last_administrator(self):
        """ Refuse to hide the Settings app from, or to block the login of, the
        last user who can undo it. """
        settings_group = self.env.ref('base.group_system', raise_if_not_found=False)
        if not settings_group:
            return
        exempt = self._exempt_user_ids()
        for profile in self:
            limits_sign_in = profile.block_login or profile.login_slot_ids or profile.allowed_ips
            if not (profile.active and profile.apply_to_admin
                    and (profile.hide_settings_menu or limits_sign_in)):
                continue
            remaining = settings_group.sudo().all_user_ids.filtered(
                lambda user: user.id in exempt or user not in profile.user_ids
            )
            if not remaining:
                if limits_sign_in:
                    raise ValidationError(_(
                        "Profile %s would block the login of every user who "
                        "could undo it. Leave at least one Settings user out of "
                        "it.", profile.name))
                raise ValidationError(_(
                    "Profile %s would hide the Settings app from every user who "
                    "could put it back. Leave at least one Settings user out of "
                    "it.", profile.name))

    #
    # actions of the single screen
    #

    def action_open_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Users'),
            'res_model': 'res.users',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.user_ids.ids)],
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
    def _om_eval_context(self):
        """ The record filter eval context: a standard access domain's, plus uid. """
        return dict(self.env['ir.access']._eval_context(), uid=self.env.uid)

    @api.model
    def om_menu_tree(self):
        """ Every menu, for the menu tree of the Menus & Apps tab. Read with
        sudo: a menu the administrator cannot see may still need hiding. """
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only the administrators can edit access profiles."))
        menus = self.env['ir.ui.menu'].sudo().search([])
        return [{
            'id': menu.id,
            'name': menu.name,
            'parent_id': menu.parent_id.id,
        } for menu in menus]

    def action_load_models(self):
        return self._open_wizard('om.access.load.models', _('Load Models'))

    def action_restrict_app(self):
        return self._open_wizard('om.access.app.wizard', _('Restrict an App'))

    def action_scan_buttons(self):
        return self._open_wizard('om.access.scan.buttons', _('Scan Buttons'))

    def action_test_user(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Effective Access'),
            'res_model': 'om.access.test.user',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_user_id': self.user_ids[:1].id},
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

        # the allowed records: one more filter on every model of their kind
        for model_name, domain in profile._allowed_filters(user).items():
            for operation in OPERATIONS:
                domains[(model_name, operation)] = domains.get((model_name, operation), ()) + (domain,)

        field_modes, field_options, field_domains = {}, {}, {}
        for line in profile.field_ids:
            model_name, field_name = line.model_id.model, line.field_id.name
            if not (model_name and field_name):
                continue
            key = (model_name, field_name)
            if line.mode != 'keep':
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
            if line.model_id.model
        )

        buttons = tuple(
            (line.model_id.model, line.view_type, line.button_type,
             line.button_name, line.button_id or '', line.mode)
            for line in profile.button_ids
            if line.model_id.model and line.button_name
        )

        menus = frozenset()
        if profile.hidden_menu_ids:
            menus = frozenset(self.env['ir.ui.menu'].sudo().with_context(active_test=False).search(
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
        )

    @api.model
    @api.ormcache('uid')
    def _resolve(self, uid):
        """ The profiles that apply to ``uid``, frozen and cached per user. """
        if uid in self._exempt_user_ids():
            return NO_RULES
        user = self.env['res.users'].sudo().browse(uid)
        if not user.exists():
            return NO_RULES
        profiles = user.access_profile_ids.sudo().filtered('active')
        if profiles:
            # Follows the user's companies, not the company switcher: core
            # caches menus per user without the company in the key.
            companies = set(user.company_ids._ids)
            profiles = profiles.filtered(
                lambda profile: not profile.company_id or profile.company_id.id in companies)
        if profiles and user._has_group('base.group_system'):
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
    def _check_button(self, model_name, button_type, name):
        rules = self._current_rules()
        if rules.enabled and rules.blocks_button(model_name, button_type, name):
            raise AccessError(_(
                "You are not allowed to use this button.\n\n"
                "Your access profile blocks '%(button)s' on '%(model)s'.",
                button=name, model=model_name))

    @api.model
    def _check_action(self, action_id):
        rules = self._current_rules()
        if not rules.enabled or not action_id:
            return
        if (rules.hides_report(action_id)
                or rules.hides_action(action_id)
                or rules.blocks_action(action_id)
                or self._hides_menu_of(rules, action_id)):
            raise AccessError(_(
                "You are not allowed to run this action.\n\n"
                "Your access profile hides it."))

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
    # view rewriting, called from Base.get_view()
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

    @staticmethod
    def _merge_domain(existing, extra):
        """ AND a value filter into the domain a field node already carries.

        Returns None unless both are plain literals, so the view keeps its own
        domain, which usually carries business logic.
        """
        existing = (existing or '').strip()
        if not existing:
            return extra
        try:
            left = ast.literal_eval(existing)
            right = ast.literal_eval(extra)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(left, list) or not isinstance(right, list):
            return None
        return repr(left + right)

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
        node.set('column_invisible' if container in ('list', 'tree') else 'invisible', '1')
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

        Cosmetic only: enforcement lives in Base._access_domain(), the field
        guard and the controllers.
        """
        lock_statusbar = rules.has_flag('lock_statusbar')
        hide_activities = rules.has_flag('hide_activities')
        chatter_hidden = {}

        for node, node_model in list(self._iter_nodes(tree, model_name)):
            tag = node.tag

            if tag == 'chatter':
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
                    if rules.field_option(node_model, field_name, 'no_open'):
                        self._set_option(node, 'no_open', True)
                    if rules.field_option(node_model, field_name, 'no_create'):
                        self._set_option(node, 'no_create', True)
                        self._set_option(node, 'no_quick_create', True)
                        self._set_option(node, 'no_create_edit', True)
                    value_filter = rules.field_domain(node_model, field_name)
                    if value_filter:
                        merged = self._merge_domain(node.get('domain'), value_filter)
                        if merged:
                            node.set('domain', merged)
                if lock_statusbar and node.get('widget') == 'statusbar':
                    self._set_option(node, 'clickable', False)
                continue

            if tag == 'button' and node.get('name') and not node.get('special') and node_model:
                if rules.hides_button(node_model, view_type, node.get('type') or 'object',
                                      node.get('name'), node.get('id') or ''):
                    self._drop(node)
                continue

            if tag == 'page' and node_model:
                if rules.hides_element(node_model, 'page', node.get('name') or ''):
                    self._drop(node)
                continue

            if tag == 'filter' and node_model:
                # a group by is a <filter> node too, so this covers both
                if rules.hides_element(node_model, 'filter', node.get('name') or ''):
                    self._drop(node)
                continue

            if tag == 'searchpanel' and node_model:
                if rules.hides_element(node_model, 'searchpanel'):
                    self._drop(node)

        if tree.tag in ('form', 'list', 'kanban'):
            if rules.model_flag(model_name, 'hide_export'):
                tree.set('export_xlsx', '0')
            if rules.model_flag(model_name, 'hide_import'):
                # base_import reads this to offer the Import menu entry
                tree.set('import', '0')
            if rules.model_flag(model_name, 'hide_duplicate'):
                tree.set('duplicate', '0')
        return tree
