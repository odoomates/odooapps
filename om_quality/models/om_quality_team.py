import ast

from odoo import fields, models
from odoo.fields import Domain


class OmQualityTeam(models.Model):
    _name = 'om.quality.team'
    _description = 'Quality Team'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, name'
    _check_company_auto = True

    def _default_stage_ids(self):
        Stage = self.env['om.quality.alert.stage']
        return Stage.search([('team_ids', '=', False)]) or Stage.search([])

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Team Leader', tracking=True, check_company=True,
        domain="[('share', '=', False)]")
    member_ids = fields.Many2many(
        'res.users', 'om_quality_team_member_rel', 'team_id', 'user_id', string='Members',
        check_company=True, domain="[('share', '=', False)]")
    stage_ids = fields.Many2many(
        'om.quality.alert.stage', 'om_quality_stage_team_rel', 'team_id', 'stage_id', string='Stages',
        default=_default_stage_ids,
        help="Stages a non-conformance of this team goes through.")
    point_ids = fields.One2many('om.quality.point', 'team_id', string='Control Points')
    check_ids = fields.One2many('om.quality.check', 'team_id', string='Checks')
    alert_ids = fields.One2many('om.quality.alert', 'team_id', string='Non-conformances')

    check_todo_count = fields.Integer(compute='_compute_counts', string='Checks to Do')
    check_failed_count = fields.Integer(compute='_compute_counts', string='Failed Checks (30 Days)')
    alert_open_count = fields.Integer(compute='_compute_counts', string='Open Non-conformances')
    alert_urgent_count = fields.Integer(compute='_compute_counts', string='Urgent Non-conformances')
    action_late_count = fields.Integer(compute='_compute_counts', string='Late Actions')
    point_count = fields.Integer(compute='_compute_counts', string='Control Points Count')

    def _compute_counts(self):
        Check = self.env['om.quality.check']
        Alert = self.env['om.quality.alert']
        team_domain = Domain('team_id', 'in', self.ids)
        month_ago = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        todo = dict(Check._read_group(team_domain & Domain('state', '=', 'todo'), ['team_id'], ['__count']))
        failed = dict(Check._read_group(
            team_domain & Domain('state', '=', 'failed') & Domain('date_done', '>=', month_ago),
            ['team_id'], ['__count']))
        alerts = dict(Alert._read_group(team_domain & Domain('is_closed', '=', False), ['team_id'], ['__count']))
        urgent = dict(Alert._read_group(
            team_domain & Domain('is_closed', '=', False) & Domain('priority', '=', '3'), ['team_id'], ['__count']))
        late = dict(self.env['om.quality.action']._read_group(
            [('alert_id.team_id', 'in', self.ids), ('state', '=', 'open'),
             ('date_deadline', '<', fields.Date.context_today(self))],
            ['alert_id.team_id'], ['__count']))
        points = dict(self.env['om.quality.point']._read_group(team_domain, ['team_id'], ['__count']))
        for team in self:
            team.check_todo_count = todo.get(team, 0)
            team.check_failed_count = failed.get(team, 0)
            team.alert_open_count = alerts.get(team, 0)
            team.alert_urgent_count = urgent.get(team, 0)
            team.action_late_count = late.get(team, 0)
            team.point_count = points.get(team, 0)

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('om.quality.alert').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['team_id'] = self.id
        return values

    def _action_for(self, xmlid, domain, context=None, name=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['display_name'] = name or self.name
        action['domain'] = domain
        action['context'] = {'default_team_id': self.id, **(context or {})}
        return action

    def action_view_checks_todo(self):
        return self._action_for(
            'om_quality.action_om_quality_check', [('team_id', '=', self.id), ('state', '=', 'todo')],
            name=self.env._('%s: Checks to Do', self.name))

    def action_view_checks_failed(self):
        return self._action_for(
            'om_quality.action_om_quality_check', [('team_id', '=', self.id), ('state', '=', 'failed')],
            name=self.env._('%s: Failed Checks', self.name))

    def action_view_alerts(self):
        return self._action_for(
            'om_quality.action_om_quality_alert', [('team_id', '=', self.id)], {'search_default_open': 1})

    def action_view_alerts_urgent(self):
        return self._action_for(
            'om_quality.action_om_quality_alert', [('team_id', '=', self.id), ('priority', '=', '3')],
            {'search_default_open': 1}, name=self.env._('%s: Urgent', self.name))

    def action_view_actions_late(self):
        return self._action_for(
            'om_quality.action_om_quality_action',
            [('alert_id.team_id', '=', self.id), ('state', '=', 'open'),
             ('date_deadline', '<', fields.Date.context_today(self))],
            name=self.env._('%s: Late Actions', self.name))

    def action_view_points(self):
        return self._action_for('om_quality.action_om_quality_point', [('team_id', '=', self.id)])
