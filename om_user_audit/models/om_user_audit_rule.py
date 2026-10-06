# What is logged. With no rule, every operation on every business model; as soon
# as a rule exists, only what the rules name.
from fnmatch import fnmatchcase

from odoo import api, fields, models, SUPERUSER_ID, tools
from odoo.tools import frozendict

OPERATIONS = ('read', 'create', 'write', 'unlink', 'export', 'import', 'print')
# models that would only log the logger, Odoo's own bookkeeping or the web
# client's noise
DEFAULT_EXCLUDED = (
    'ir.*', 'bus.*', 'base.*', 'base_import.*', 'web_tour.*', 'res.users.log', 'res.users.settings*',
    'res.device*', 'res.session*', 'mail.tracking.value', 'mail.notification', 'mail.followers',
    'mail.mail', 'mail.message.schedule', 'mail.link.preview', 'mail.presence', 'discuss.channel.member',
    'om.user.audit.*', 'res.config*', 'digest.*', 'auth_totp.device', 'iap.*', 'spreadsheet.*revision*',
)
DEFAULT_KEPT = ('ir.attachment',)


class OmUserAuditRule(models.Model):
    _name = 'om.user.audit.rule'
    _description = 'User Audit Rule'
    _order = 'sequence, id'
    # the parameters are cached there too: a parameter changed by hand reaches the rules
    _clear_cache_name = 'default'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_ids = fields.Many2many(
        'ir.model', 'om_user_audit_rule_model_rel', 'rule_id', 'model_id', string='Data',
        domain=[('transient', '=', False)],
        help="Left empty, the rule covers every kind of data but the technical ones.")
    user_ids = fields.Many2many('res.users', 'om_user_audit_rule_user_rel', 'rule_id', 'user_id',
                                string='Users')
    group_ids = fields.Many2many('res.groups', 'om_user_audit_rule_group_rel', 'rule_id', 'group_id',
                                 string='Groups',
                                 help="With neither users nor groups, the rule covers everyone.")
    log_read = fields.Boolean(string='Read')
    log_create = fields.Boolean(string='Create', default=True)
    log_write = fields.Boolean(string='Edit', default=True)
    log_unlink = fields.Boolean(string='Delete', default=True)
    log_export = fields.Boolean(string='Export', default=True)
    log_import = fields.Boolean(string='Import', default=True)
    log_print = fields.Boolean(string='Print', default=True)

    @api.model
    @tools.ormcache(cache='default')
    def _om_policy(self):
        """ The rules and settings, frozen. """
        params = self.env['ir.config_parameter'].sudo()
        excluded = params.get_str('om_user_audit.excluded_models')
        excluded = tuple(filter(None, (part.strip() for part in excluded.replace('\n', ',').split(',')))) \
            or DEFAULT_EXCLUDED
        rules = tuple(
            frozendict(
                models=frozenset(rule.model_ids.mapped('model')) or None,
                operations=frozenset(op for op in OPERATIONS if rule[f'log_{op}']),
                users=frozenset(rule.user_ids.ids),
                groups=frozenset(rule.group_ids.ids),
            )
            for rule in self.sudo().search([])
        )
        return frozendict(
            rules=rules,
            excluded=excluded,
            log_reads=params.get_bool('om_user_audit.log_reads', True),
        )

    @api.model
    def _om_excluded(self, model_name, policy):
        if model_name in DEFAULT_KEPT:
            return False
        return any(fnmatchcase(model_name, pattern) for pattern in policy['excluded'])

    @api.model
    @tools.ormcache('model_name', 'operation', 'uid', cache='default')
    def _om_should_log(self, model_name, operation, uid):
        if not uid or uid == SUPERUSER_ID:
            return False
        policy = self._om_policy()
        if operation == 'read' and not policy['log_reads']:
            return False
        model = self.env.get(model_name)
        if model is None or model._transient or model._abstract:
            return False
        if not policy['rules']:
            return not self._om_excluded(model_name, policy)
        user_groups = None
        for rule in policy['rules']:
            if operation not in rule['operations']:
                continue
            if rule['models'] is None:
                if self._om_excluded(model_name, policy):
                    continue
            elif model_name not in rule['models']:
                continue
            if rule['users'] or rule['groups']:
                if uid not in rule['users']:
                    if user_groups is None:
                        user_groups = set(self.env['res.users'].sudo().browse(uid).groups_id.ids)
                    if not rule['groups'] & user_groups:
                        continue
            return True
        return False
