from markupsafe import Markup, escape

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

NOTE_MODES = [('none', 'Not Asked'), ('optional', 'Optional'), ('required', 'Required')]

# how the summary of a flow reads the operators of its conditions
OPERATORS = {
    '=': '=', '!=': '≠', '>': '>', '>=': '≥', '<': '<', '<=': '≤', 'in': 'in', 'not in': 'not in',
    'ilike': 'contains', 'not ilike': 'does not contain', 'like': 'contains', 'not like': 'does not contain',
}


def _literal_domain(env, domain):
    return Domain(safe_eval(domain or '[]', {'context': env.context, 'user': env.user}))


class ApprovalFlow(models.Model):
    """ Who approves, in which order, before a button of a model runs or before a document is approved. """
    _name = 'approval.rule'
    _description = 'Approval Flow'
    _order = 'sequence, id'
    # _locked_models
    _clear_cache_name = 'default'
    _clear_cache_on_fields = ('button_id', 'lock_record', 'active', 'model_id')

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', index=True,
                               domain=[('transient', '=', False)])
    model = fields.Char(related='model_id.model', store=True, string='Model Name')
    is_document = fields.Boolean(compute='_compute_is_document')
    button_id = fields.Many2one(
        'approval.button', ondelete='cascade', domain="[('model_id', '=', model_id)]",
        help='The button stopped until the approval is given. Leave it empty on a document approved by its own '
             'Submit button, such as an HR request.')
    method = fields.Char(related='button_id.method', store=True, index=True)
    company_id = fields.Many2one('res.company', help='Empty: the flow applies to every company.')
    domain = fields.Char(
        string='Applies To', default='[]',
        help='The records the flow applies to, e.g. the sale orders above 10,000. The first matching flow is used.')
    step_ids = fields.One2many('approval.step', 'flow_id', string='Steps', copy=True)
    fallback_group_id = fields.Many2one(
        'res.groups', string='Approvers When Nobody Is Found',
        default=lambda self: self.env.ref('om_approval.group_approval_manager', raise_if_not_found=False),
        help='Approve a step finding nobody, e.g. an employee without a manager.')
    self_approve = fields.Boolean(
        string='Requester Approves Their Steps', default=True,
        help='The steps the requester is an approver of are approved as they ask, e.g. a sales manager confirming '
             'their own order. Otherwise somebody else approves them.')
    run_on_approval = fields.Boolean(
        string='Run the Button Once Approved', default=True,
        help='Once approved, the button runs as the requester. Otherwise the requester clicks it again.')
    note = fields.Text(string='Message to the Requester', translate=True,
                       help='Shown when the button is stopped, e.g. "Orders above 10,000 need the approval of the '
                            'sales director."')
    lock_record = fields.Boolean(
        string='Lock the Record', default=True,
        help='The record is read-only from the approval request: nobody changes it while it waits, nor once it is '
             'approved.')
    lock_after = fields.Selection([
        ('unlock', 'Unlock Once the Button Has Run'),
        ('keep', 'Keep It Locked'),
    ], string='Once Approved', required=True, default='unlock',
        help='Unlock: the record is editable again once the approved button has run, as the button leaves it. '
             'Keep it locked: it stays read-only until an approval manager unlocks it.')
    summary = fields.Html(compute='_compute_summary', sanitize=False,
                          help='What the flow does, in words.')
    amount_field = fields.Char(
        string='Amount',
        help='The amount the flow and its steps compare, e.g. amount_total for the total of a sale order. It is '
             'converted from the currency of the record into the currency of the flow.')
    amount_min = fields.Float(string='Above', help='The flow applies to the records whose amount is above this.')
    amount_currency_id = fields.Many2one(
        'res.currency', string='Currency', default=lambda self: self.env.company.currency_id,
        help='The currency of the amounts of the flow and of its steps.')
    request_note = fields.Selection(NOTE_MODES, string="Requester's Note", required=True, default='optional',
                                    help='Asked when the button is clicked: why the approval is needed, with files.')
    approve_note = fields.Selection(NOTE_MODES, string='Note When Approving', required=True, default='optional')
    refuse_note = fields.Selection(NOTE_MODES, string='Note When Refusing', required=True, default='required')

    @api.depends('model')
    def _compute_is_document(self):
        documents = set(self.env['approval.mixin']._inherit_children)
        for flow in self:
            flow.is_document = flow.model in documents

    @api.depends('name', 'model_id', 'button_id', 'domain', 'self_approve', 'run_on_approval', 'fallback_group_id',
                 'lock_record', 'lock_after', 'step_ids', 'step_ids.name', 'step_ids.approver_type',
                 'step_ids.group_id', 'step_ids.user_ids', 'step_ids.field_path', 'step_ids.domain',
                 'step_ids.remind_days', 'step_ids.escalate_days', 'step_ids.escalate_type',
                 'step_ids.escalate_user_ids', 'step_ids.escalate_group_id', 'step_ids.sequence',
                 'amount_field', 'amount_min', 'amount_currency_id', 'request_note', 'approve_note', 'refuse_note',
                 'step_ids.amount_min', 'step_ids.approval_mode', 'step_ids.approval_count')
    def _compute_summary(self):
        for flow in self:
            flow.summary = flow._summary() if flow.model_id else False

    def _summary(self):
        """ :return: what the flow does, in words, as HTML """
        self.ensure_one()
        model = self.model_id.name
        conditions = self._describe_conditions()
        if self.button_id:
            intro = self.env._('When %(button)s is clicked on a %(model)s', button=self._bold(self.button_id.name),
                               model=self._bold(model))
        else:
            intro = self.env._('When a %(model)s is submitted', model=self._bold(model))
        if conditions:
            intro = self.env._('%(intro)s with %(conditions)s', intro=intro, conditions=conditions)
        steps = self.step_ids.sorted(lambda s: (s.sequence, s.id))
        if steps:
            items = Markup('').join(Markup('<li>%s</li>') % step._summary() for step in steps)
            parts = [Markup('<p>%s</p><ol>%s</ol>') % (self.env._('%s, it waits for:', intro), items)]
        else:
            parts = [Markup('<p>%s</p>') % self.env._('%(intro)s, it waits for the approval of %(group)s.',
                                                       intro=intro, group=self._bold(self._fallback_name()))]
        notes = []
        if steps:
            notes.append(self.env._('When a step finds nobody: %s.', self._bold(self._fallback_name())))
        notes.append(self.env._('The requester approves the steps they are an approver of.') if self.self_approve
                     else self.env._('The requester does not approve their own request.'))
        modes = {'optional': self.env._('optional'), 'required': self.env._('required')}
        if self.button_id and self.request_note != 'none':
            notes.append(self.env._("The requester's note, with files: %s.", modes[self.request_note]))
        decisions = [text % modes[mode] for text, mode in (
            (self.env._('%s when approving'), self.approve_note),
            (self.env._('%s when refusing'), self.refuse_note)) if mode != 'none']
        if decisions:
            notes.append(self.env._("The approver's note: %s.", ', '.join(decisions)))
        if self.button_id:
            button = self._bold(self.button_id.name)
            notes.append(self.env._('Once approved, %s runs by itself as the requester.', button)
                         if self.run_on_approval
                         else self.env._('Once approved, the requester clicks %s again.', button))
            if self.lock_record and self.lock_after == 'keep':
                notes.append(self.env._('The record is read-only from the request on, and stays so once approved, '
                                        'until an approval manager unlocks it.'))
            elif self.lock_record:
                notes.append(self.env._('The record is read-only from the request until %s has run.', button))
            else:
                notes.append(self.env._('The record can still be changed while it waits.'))
        parts.append(Markup('<ul class="mb-0">%s</ul>') % Markup('').join(
            Markup('<li>%s</li>') % note for note in notes))
        return Markup('').join(parts)

    @api.model
    def _bold(self, text):
        return Markup('<strong>%s</strong>') % (text or '')

    def _fallback_name(self):
        group = self.fallback_group_id or self.env.ref('om_approval.group_approval_manager', raise_if_not_found=False)
        return group.sudo().full_name if group else self.env._('the approval administrators')

    def _describe_conditions(self):
        """ :return: the domain and the amount of the flow in words, False for none """
        self.ensure_one()
        parts = [part for part in (self._describe_domain(self.domain), self._describe_amount(self.amount_min))
                 if part]
        if not parts:
            return False
        return Markup(' %s ' % escape(self.env._('and'))).join(
            part if isinstance(part, Markup) else Markup('<em>%s</em>') % part for part in parts)

    def _describe_domain(self, domain):
        """ :return: the conditions of `domain` in words, e.g. Total > 1,500, or False for none """
        self.ensure_one()
        try:
            leaves = safe_eval(domain or '[]', {'context': self.env.context, 'user': self.env.user})
        except Exception:  # an invalid domain is reported when it is used; the summary only shows it
            return escape(domain or '')
        if not leaves:
            return False
        if any(not isinstance(leaf, (list, tuple)) or len(leaf) != 3 for leaf in leaves):
            return self.env._('the conditions of Applies To')
        model = self.env[self.model] if self.model in self.env else None
        words = [self._describe_leaf(model, *leaf) for leaf in leaves]
        return Markup(' %s ' % escape(self.env._('and'))).join(Markup('<em>%s</em>') % word for word in words)

    def _describe_leaf(self, model, path, operator, value):
        label, field = path, None
        if model is not None:
            labels = []
            current = model
            for name in str(path).split('.'):
                field = current._fields.get(name)
                if field is None:
                    labels = [str(path)]
                    break
                labels.append(field._description_string(self.env))
                if field.relational:
                    current = self.env[field.comodel_name]
            label = ' › '.join(labels)
        if field is not None and field.relational and value and value is not True:
            ids = value if isinstance(value, (list, tuple)) else [value]
            if all(isinstance(i, int) for i in ids):
                value = ', '.join(self.env[field.comodel_name].sudo().browse(ids).exists().mapped('display_name'))
        elif field is not None and field.type == 'selection' and isinstance(value, str):
            value = dict(field._description_selection(self.env)).get(value, value)
        elif isinstance(value, float) or (isinstance(value, int) and not isinstance(value, bool)):
            value = tools.format_amount(self.env, value, self.env.company.currency_id) \
                if field is not None and field.type == 'monetary' else f'{value:,}'
        if value is False and operator in ('=', '!='):
            return self.env._('%s is set', label) if operator == '!=' else self.env._('%s is not set', label)
        return '%s %s %s' % (label, OPERATORS.get(operator, operator), value)

    def _literal_domain(self):
        self.ensure_one()
        return _literal_domain(self.env, self.domain)

    def _simulate(self, record):
        """ :return: what the flow would do for `record` if the current user asked, as HTML; nothing is created """
        self.ensure_one()
        user = self.env.user
        bold = self._bold
        first = self._get_flow(record, self.method or False)
        if not record.filtered_domain(self._literal_domain()) or not self._amount_applies(record):
            return Markup('<div class="alert alert-info mb-0">%s</div>') % self.env._(
                'The flow does not apply to %(record)s: it is outside Applies To, so %(action)s.',
                record=bold(record.display_name),
                action=self.env._('%s runs without an approval', self.button_id.name) if self.button_id
                else self.env._('it is approved by the approval administrators'))
        parts = []
        if first and first != self:
            parts.append(Markup('<div class="alert alert-warning">%s</div>') % self.env._(
                '%(other)s applies to %(record)s first: it comes before this flow in the list.',
                other=bold(first.name), record=bold(record.display_name)))
        request = self.env['approval.request'].new({
            'flow_id': self.id, 'res_model': record._name, 'res_id': record.id, 'requester_id': user.id,
            'method': self.method or False, 'company_id': self._record_company(record).id,
        })
        rows = []
        steps = self.step_ids.sorted(lambda s: (s.sequence, s.id))
        for step in steps:
            if not step._applies_to(record):
                rows.append((step.name, False, self.env._('Skipped: %s is outside its condition.',
                                                           record.display_name)))
                continue
            approvers = step._get_approvers(request, record)
            names = ', '.join(approvers.mapped('name')) or self.env._('nobody')
            if self.self_approve and user in approvers:
                rows.append((step.name, True, self.env._('%(names)s. Approved at once: %(user)s asks and is one of '
                                                         'them.', names=names, user=user.name)))
            elif step.approval_mode == 'all' and len(approvers) > 1:
                rows.append((step.name, True, self.env._('%s, all of them', names)))
            elif step.approval_mode == 'count':
                rows.append((step.name, True, self.env._('%(count)s of %(names)s', count=step.approval_count,
                                                         names=names)))
            else:
                rows.append((step.name, True, names))
        if not steps:
            fallback = request._fallback_approvers(self.fallback_group_id)
            approvers = (fallback - request._excluded_approvers()) or fallback
            rows.append((self.env._('Approval'), True, ', '.join(approvers.mapped('name')) or self.env._('nobody')))
        body = Markup('').join(
            Markup('<tr class="%s"><td>%s</td><td>%s</td></tr>') % ('' if applies else 'text-muted', name, who)
            for name, applies, who in rows)
        amount = self._record_amount(record)
        if amount is not None:
            parts.append(Markup('<p>%s</p>') % self.env._(
                '%(field)s of %(record)s: %(amount)s.', field=self._describe_path(self.amount_field),
                record=bold(record.display_name), amount=bold(self._format_amount(amount))))
        parts.append(Markup('<p>%s</p>') % self.env._('If %(user)s asked for %(record)s, it would wait for:',
                                                      user=bold(user.name), record=bold(record.display_name)))
        parts.append(Markup('<table class="table table-sm"><thead><tr><th>%s</th><th>%s</th></tr></thead>'
                            '<tbody>%s</tbody></table>') % (self.env._('Step'), self.env._('Approvers'), body))
        if self.button_id and self.lock_record:
            parts.append(Markup('<p class="mb-0">%s</p>') % (
                self.env._('%s would be read-only from the request, and stay so once approved until an approval '
                           'manager unlocks it.', bold(record.display_name)) if self.lock_after == 'keep'
                else self.env._('%(record)s would be read-only from the request until %(button)s has run.',
                                record=bold(record.display_name), button=bold(self.button_id.name))))
        return Markup('').join(parts)

    def action_simulate(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Test %s', self.name),
            'res_model': 'approval.simulate',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_flow_id': self.id},
        }

    @api.model
    @api.ormcache()
    def _locked_models(self):
        """ :return: the models a flow locks the records of while they wait for an approval """
        flows = self.sudo().search([('button_id', '!=', False), ('lock_record', '=', True)])
        return frozenset(flows.mapped('model'))

    @api.constrains('model_id', 'amount_field', 'amount_min')
    def _check_amount_field(self):
        for flow in self.filtered('amount_field'):
            field = flow._amount_field_def()
            if field is None or field.type not in ('monetary', 'float', 'integer'):
                raise ValidationError(self.env._('%(path)s is not an amount of %(model)s.',
                                                 path=flow.amount_field, model=flow.model_id.name))

    def _amount_field_def(self):
        """ :return: the field the amount path leads to, None when the path is wrong """
        self.ensure_one()
        if not self.amount_field or self.model not in self.env:
            return None
        model = self.env[self.model]
        field = None
        for name in self.amount_field.split('.'):
            field = model._fields.get(name) if model is not None else None
            if field is None:
                return None
            model = self.env[field.comodel_name] if field.relational else None
        return field

    def _record_amount(self, record):
        """ :return: the amount of `record` in the currency of the flow, None when the flow has no amount """
        self.ensure_one()
        field = self._amount_field_def()
        if field is None:
            return None
        *path, name = self.amount_field.split('.')
        holder = record.sudo().mapped('.'.join(path))[:1] if path else record.sudo()
        if not holder:
            return 0.0
        value = holder[name] or 0.0
        currency = self.amount_currency_id
        if field.type == 'monetary' and currency:
            source = holder[field.get_currency_field(holder)]
            if source and source != currency:
                company = self._record_company(record)
                value = source._convert(value, currency, company, fields.Date.context_today(self))
        return value

    def _amount_applies(self, record, minimum=None):
        """ :return: whether the amount of `record` is above `minimum`, by default the amount of the flow """
        self.ensure_one()
        minimum = self.amount_min if minimum is None else minimum
        if not self.amount_field or not minimum:
            return True
        amount = self._record_amount(record)
        return amount is None or amount > minimum

    def _format_amount(self, amount):
        self.ensure_one()
        currency = self.amount_currency_id
        return tools.format_amount(self.env, amount, currency) if currency else f'{amount:,}'

    def _describe_amount(self, minimum):
        """ :return: e.g. Total above $ 5,000.00, False when the flow compares no amount """
        self.ensure_one()
        field = self._amount_field_def()
        if field is None or not minimum:
            return False
        return self.env._('%(amount)s above %(minimum)s', amount=self._describe_path(self.amount_field),
                          minimum=self._format_amount(minimum))

    def _describe_path(self, path):
        """ :return: the labels of a field path, e.g. Sales Team › Team Leader """
        self.ensure_one()
        model = self.env[self.model] if self.model in self.env else None
        labels = []
        for name in (path or '').split('.'):
            field = model._fields.get(name) if model is not None else None
            if field is None:
                return path or '?'
            labels.append(field._description_string(self.env))
            model = self.env[field.comodel_name] if field.relational else None
        return ' › '.join(labels)

    @api.constrains('model_id', 'button_id')
    def _check_button_model(self):
        for flow in self:
            if flow.button_id and flow.button_id.model_id != flow.model_id:
                raise ValidationError(self.env._('The button of the flow %s belongs to another model.', flow.name))
            if not flow.button_id and not flow.is_document:
                raise ValidationError(self.env._(
                    'Choose the button the flow %(flow)s stops: %(model)s has no approval of its own.',
                    flow=flow.name, model=flow.model_id.name))

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.model_id:
            self.env['approval.button']._sync(self.model_id.model)
        if self.button_id.model_id != self.model_id:
            self.button_id = False

    def action_refresh_buttons(self):
        for flow in self:
            self.env['approval.button']._sync(flow.model)
        return True

    @api.model
    def _get_flow(self, record, method=False):
        """ :return: the first active flow of `record` for the button `method`, or for the document itself when
                     no method is given, matching the record; or an empty recordset """
        flows = self.sudo().search([
            ('model', '=', record._name),
            ('method', '=', method or False),
            ('company_id', 'in', [False, self._record_company(record).id]),
        ])
        for flow in flows:
            if record.sudo().filtered_domain(_literal_domain(self.env, flow.domain)) and flow._amount_applies(record):
                return flow
        return flows.browse()

    @api.model
    def _record_company(self, record):
        if 'company_id' in record._fields and record.company_id:
            return record.company_id
        return self.env.company

    @api.model
    def _has_button_flows(self, model, method):
        """ Quick test made on every button click, before reading the records. """
        return bool(self.sudo().search_count([('model', '=', model), ('method', '=', method)], limit=1))


class ApprovalStep(models.Model):
    """ One approval of a flow, and who gives it. """
    _name = 'approval.step'
    _description = 'Approval Step'
    _order = 'sequence, id'

    flow_id = fields.Many2one('approval.rule', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='flow_id.model')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    approver_type = fields.Selection([
        ('user', 'Specific People'),
        ('group', 'Users of a Group'),
        ('field', 'Person on the Record'),
    ], string='Approver', required=True, default='group')
    group_id = fields.Many2one('res.groups')
    user_ids = fields.Many2many('res.users', string='Users')
    field_path = fields.Char(
        string='Field', help='The field of the record naming the approver, e.g. user_id for the salesperson of a sale '
                             'order, or team_id.user_id for the leader of its sales team.')
    domain = fields.Char(
        string='Only When', default='[]',
        help='The step is skipped for the records outside this domain, e.g. an amount above a threshold.')
    remind_days = fields.Integer(string='Remind After', help='Days before the approvers are reminded, then again '
                                                             'every as many days. 0 for no reminder.')
    escalate_days = fields.Integer(string='Escalate After', help='Days before other users are asked to decide '
                                                                 'too. 0 for no escalation.')
    escalate_type = fields.Selection([
        ('fallback', 'Fallback Group of the Flow'),
        ('user', 'Specific People'),
        ('group', 'Users of a Group'),
    ], string='Escalate To', required=True, default=lambda self: self._default_escalate_type())
    escalate_user_ids = fields.Many2many('res.users', 'approval_step_escalate_user_rel', string='Escalation Users')
    amount_min = fields.Float(
        string='Only Above', help='The step applies to the records whose amount, as the flow reads it, is above this. '
                                  '0 for any amount.')
    approval_mode = fields.Selection([
        ('any', 'Any One of Them'),
        ('all', 'All of Them'),
        ('count', 'A Number of Them'),
    ], string='Who Must Approve', required=True, default='any',
        help='Any one: the first approval decides. All: each approver approves. A number: that many approve. '
             'A refusal refuses the step.')
    approval_count = fields.Integer(string='How Many', default=2)
    escalate_group_id = fields.Many2one('res.groups', string='Escalation Group')

    @api.constrains('approval_mode', 'approval_count')
    def _check_approval_count(self):
        for step in self:
            if step.approval_mode == 'count' and step.approval_count < 1:
                raise ValidationError(self.env._('At least one person approves the step %s.', step.name))

    @api.constrains('approver_type', 'group_id', 'user_ids', 'field_path')
    def _check_approver(self):
        for step in self:
            if step.approver_type == 'group' and not step.group_id:
                raise ValidationError(self.env._('Choose the group approving the step %s.', step.name))
            if step.approver_type == 'user' and not step.user_ids:
                raise ValidationError(self.env._('Choose the users approving the step %s.', step.name))
            if step.approver_type == 'field':
                step._check_field_path()

    def _check_field_path(self):
        self.ensure_one()
        model = self.env[self.flow_id.model]
        try:
            for name in (self.field_path or '').split('.'):
                model = self.env[model._fields[name].comodel_name]
        except (KeyError, AttributeError):
            raise ValidationError(self.env._('%(path)s is not a field path of %(model)s.',
                                             path=self.field_path, model=self.flow_id.model_id.name)) from None
        if model._name not in self._users_models():
            raise ValidationError(self.env._('The field %s must lead to users, employees or contacts.',
                                             self.field_path))

    @api.model
    def _users_models(self):
        return ('res.users', 'res.partner')

    def _applies_to(self, record):
        self.ensure_one()
        return bool(record.sudo().filtered_domain(_literal_domain(self.env, self.domain))) and (
            not self.amount_min or self.flow_id._amount_applies(record, self.amount_min))

    def _get_approvers(self, request, record):
        """ :return: the users approving the step for `record`, or the fallback group of the flow when nobody is
                     found. Unless the requester approves his own steps, the users `request` excludes, i.e. the
                     requester, approve only when nobody else can. """
        self.ensure_one()
        users = getattr(self, f'_approvers_{self.approver_type}')(request, record.sudo())
        users = users.filtered(lambda user: user.active and not user.share)
        if self.flow_id.self_approve:
            return users or self._fallback_approvers(request)
        excluded = request._excluded_approvers()
        fallback = self._fallback_approvers(request)
        return (users - excluded) or (fallback - excluded) or fallback

    def _approvers_user(self, request, record):
        return self.user_ids

    def _approvers_group(self, request, record):
        return self.group_id.all_user_ids

    def _approvers_field(self, request, record):
        return self._as_users(record.mapped(self.field_path))

    @api.model
    def _as_users(self, records):
        if records._name == 'res.partner':
            return records.user_ids
        return records if records._name == 'res.users' else self.env['res.users']

    def _fallback_approvers(self, request):
        return request._fallback_approvers(self.flow_id.fallback_group_id)

    @api.model
    def _default_escalate_type(self):
        return 'fallback'

    def _escalation_users(self, line):
        """ :return: the users asked to decide a step waiting too long """
        self.ensure_one()
        users = getattr(self, f'_escalate_{self.escalate_type}')(line)
        return users.filtered(lambda user: user.active and not user.share) or \
            self._escalate_fallback(line)

    def _escalate_fallback(self, line):
        return line.request_id._fallback_approvers(self.flow_id.fallback_group_id)

    def _escalate_user(self, line):
        return self.escalate_user_ids

    def _escalate_group(self, line):
        return self.escalate_group_id.all_user_ids

    def _summary(self):
        """ :return: the step in words, for the summary of its flow """
        self.ensure_one()
        flow = self.flow_id
        who = self._describe_approvers()
        text = Markup('%s: %s') % (flow._bold(self.name), who)
        extra = []
        conditions = self._describe_conditions()
        if conditions:
            extra.append(self.env._('only when %s', conditions))
        if self.approval_mode == 'all':
            extra.append(self.env._('all of them approve'))
        elif self.approval_mode == 'count':
            extra.append(self.env._('%s of them approve', self.approval_count))
        if self.remind_days:
            extra.append(self.env._('reminded after %s', self._days(self.remind_days)))
        if self.escalate_days:
            extra.append(self.env._('after %(days)s, %(users)s decide too', days=self._days(self.escalate_days),
                                    users=self._describe_escalation()))
        if extra:
            text = Markup('%s <span class="text-muted">· %s</span>') % (text, Markup(' · ').join(extra))
        return text

    def _describe_conditions(self):
        """ :return: when the step applies, in words, False for always """
        self.ensure_one()
        flow = self.flow_id
        parts = [part for part in (flow._describe_domain(self.domain), flow._describe_amount(self.amount_min))
                 if part]
        if not parts:
            return False
        return Markup(' %s ' % escape(self.env._('and'))).join(
            part if isinstance(part, Markup) else Markup('<em>%s</em>') % part for part in parts)

    def _days(self, days):
        return self.env._('1 day') if days == 1 else self.env._('%s days', days)

    def _describe_approvers(self):
        """ :return: who approves the step, in words """
        self.ensure_one()
        if self.approver_type == 'user':
            return ', '.join(self.user_ids.mapped('name')) or self.env._('nobody chosen yet')
        if self.approver_type == 'group':
            return self.env._('users of the group %s', self.group_id.sudo().full_name or '?')
        if self.approver_type == 'field':
            return self.env._('the %s of the record', self._describe_path(self.field_path))
        return dict(self._fields['approver_type']._description_selection(self.env)).get(self.approver_type)

    def _describe_escalation(self):
        self.ensure_one()
        if self.escalate_type == 'fallback':
            return self.flow_id._fallback_name()
        if self.escalate_type == 'user':
            return ', '.join(self.escalate_user_ids.mapped('name')) or '?'
        if self.escalate_type == 'group':
            return self.env._('users of the group %s', self.escalate_group_id.sudo().full_name or '?')
        return dict(self._fields['escalate_type']._description_selection(self.env)).get(self.escalate_type)

    def _describe_path(self, path):
        return self.flow_id._describe_path(path)
