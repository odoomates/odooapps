from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

# how far a chain of substitutes is followed: the substitute of a substitute, and so on
CHAIN_DEPTH = 3


class ApprovalDelegation(models.Model):
    """ An approver away for a period: their substitute approves for them meanwhile, on the steps waiting for the
    approver and on those becoming due. The approver can still decide; the first decision counts. """
    _name = 'approval.delegation'
    _inherit = ['mail.thread']
    _description = 'Approval Delegation'
    _order = 'date_from desc, id desc'

    user_id = fields.Many2one('res.users', string='Approver', required=True, index=True, tracking=True,
                              default=lambda self: self.env.user, domain=[('share', '=', False)])
    delegate_id = fields.Many2one('res.users', string='Substitute', required=True, index=True, tracking=True,
                                  domain=[('share', '=', False)],
                                  default=lambda self: self.env.user.approval_substitute_id)
    date_from = fields.Date(string='From', required=True, default=fields.Date.context_today, tracking=True)
    date_to = fields.Date(string='To', required=True, tracking=True)
    flow_ids = fields.Many2many('approval.rule', string='Only for',
                                help='Leave empty for every approval flow.')
    note = fields.Text()
    active = fields.Boolean(default=True)
    state = fields.Selection([('upcoming', 'Upcoming'), ('active', 'Active'), ('ended', 'Ended')],
                             compute='_compute_state', search='_search_state')

    @api.depends('date_from', 'date_to')
    @api.depends_context('date')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for delegation in self:
            delegation.state = 'upcoming' if delegation.date_from > today else \
                'ended' if delegation.date_to < today else 'active'

    def _search_state(self, operator, value):
        today = fields.Date.context_today(self)
        domains = {'upcoming': [('date_from', '>', today)], 'ended': [('date_to', '<', today)],
                   'active': [('date_from', '<=', today), ('date_to', '>=', today)]}
        values = [value] if isinstance(value, str) else list(value)
        if operator not in ('=', 'in') or any(v not in domains for v in values):
            raise ValidationError(self.env._('Search the status with = or in.'))
        return Domain.OR(Domain(domains[state]) for state in values)

    @api.depends('user_id', 'delegate_id')
    def _compute_display_name(self):
        for delegation in self:
            delegation.display_name = self.env._('%(user)s to %(delegate)s', user=delegation.user_id.name,
                                                 delegate=delegation.delegate_id.name)

    @api.constrains('user_id', 'delegate_id', 'date_from', 'date_to')
    def _check_delegation(self):
        for delegation in self:
            if delegation.date_to < delegation.date_from:
                raise ValidationError(self.env._('The delegation ends before it starts.'))
            if delegation.delegate_id == delegation.user_id:
                raise ValidationError(self.env._('Choose a substitute other than the approver.'))

    def _check_delegator(self):
        """ Users delegate their own approvals; the approval administrators, and the code acting as the super
            user (e.g. from the time off), those of anyone. Checked here, not in a constraint: the constraints run
            as the super user. """
        if self.env.su or self.env.user.has_group('om_approval.group_approval_manager'):
            return
        if any(delegation.user_id != self.env.user for delegation in self):
            raise ValidationError(self.env._('Delegate your own approvals: the approval administrators delegate '
                                             'those of the others.'))

    @api.model_create_multi
    def create(self, vals_list):
        delegations = super().create(vals_list)
        delegations._check_delegator()
        delegations._apply()
        return delegations

    def write(self, vals):
        self._check_delegator()
        result = super().write(vals)
        self._check_delegator()
        if {'delegate_id', 'date_from', 'date_to', 'flow_ids', 'active'} & set(vals):
            self._apply()
        return result

    def _apply(self):
        """ Give the substitutes the steps waiting now for the approvers away today. """
        users = self.filtered(lambda d: d.active and d.state == 'active').user_id
        if users:
            lines = self.env['approval.line'].sudo().search(
                [('state', '=', 'pending'), ('approver_user_ids', 'in', users.ids)])
            lines._apply_delegations()

    @api.model
    def _substitutes(self, users, flow, day=None):
        """ :return: {substitute: approvers they stand for}, for the users of `users` away on `day` and for the
                     approval flow `flow`, following the substitutes who are away too """
        day = day or fields.Date.context_today(self)
        result = {}
        seen = set(users.ids)
        current = users
        for _depth in range(CHAIN_DEPTH):
            delegations = self.sudo().search([
                ('user_id', 'in', current.ids), ('date_from', '<=', day), ('date_to', '>=', day)])
            delegations = delegations.filtered(lambda d: not d.flow_ids or flow in d.flow_ids)
            following = self.env['res.users']
            for delegation in delegations:
                delegate = delegation.delegate_id
                if delegate.id in seen or not delegate.active:
                    continue
                stands_for = result.get(delegate, self.env['res.users'])
                result[delegate] = stands_for | delegation.user_id
                following |= delegate
            seen |= set(following.ids)
            current = following
            if not current:
                break
        return result
