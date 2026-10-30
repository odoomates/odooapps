import logging
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.misc import format_datetime

from .approval_button import NOT_BUTTONS

_logger = logging.getLogger(__name__)

ACTIVITY = 'om_approval.mail_act_approval'
# the records whose approved button is running, by (model, id): the lock lets the button change them
RUNNING = 'approval_running'


class ApprovalRequest(models.Model):
    """ The approval a record waits for: for a button of the record, or for the record itself when it is a
        document with an approval of its own. Its lines are the steps of the flow, approved in turn. """
    _name = 'approval.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Approval Request'
    _check_company_auto = True
    _order = 'id desc'
    _mail_post_access = 'read'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False,
                       default=lambda self: self.env._('New'))
    flow_id = fields.Many2one('approval.rule', readonly=True, ondelete='restrict', check_company=True)
    res_model = fields.Char(string='Model', required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference(string='Record ID', model_field='res_model', required=True, readonly=True,
                                      index=True)
    model_name = fields.Char(string='Kind of Record', compute='_compute_model_name')
    document_name = fields.Char(string='Record', compute='_compute_document_name')
    method = fields.Char(string='Button Method', readonly=True)
    button_name = fields.Char(string='Button', readonly=True)
    requester_id = fields.Many2one('res.users', string='Requested By', required=True, readonly=True, index=True,
                                   default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', readonly=True, index=True)
    state = fields.Selection([
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('refused', 'Refused'),
        ('cancel', 'Cancelled'),
    ], required=True, default='to_approve', readonly=True, index=True, tracking=True,
        help='Done: the button ran once approved.')
    line_ids = fields.One2many('approval.line', 'request_id', string='Approvals', readonly=True)
    approval_step = fields.Char(string='Waiting For', compute='_compute_current')
    approver_user_ids = fields.Many2many('res.users', string='Approvers', compute='_compute_current',
                                         search='_search_approver_user_ids')
    can_approve = fields.Boolean(compute='_compute_current')
    note = fields.Text(string='Message', related='flow_id.note')
    lock_record = fields.Boolean(string='Locks the Record', readonly=True,
                                 help='The record stays read-only while it waits for this approval.')
    keep_locked = fields.Boolean(string='Stays Locked Once Approved', readonly=True,
                                 help='Once the button has run, the record stays read-only until an approval manager '
                                      'unlocks it.')
    date_unlocked = fields.Datetime(string='Unlocked On', readonly=True, copy=False)
    unlocked_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    is_locking = fields.Boolean(string='Locking', compute='_compute_is_locking',
                                help='The record is read-only because of this request.')
    request_note = fields.Text(string="Requester's Note", readonly=True,
                               help='Why the requester needs the approval.')
    attachment_ids = fields.Many2many('ir.attachment', 'approval_request_attachment_rel', 'request_id',
                                      'attachment_id', string='Files', readonly=True)
    refusal_dismissed = fields.Boolean(readonly=True, copy=False,
                                       help='The refusal no longer shows at the top of the record.')

    @api.depends('res_model')
    def _compute_model_name(self):
        for request in self:
            request.model_name = self.env['ir.model']._get(request.res_model).name if request.res_model else False

    @api.depends('res_model', 'res_id')
    def _compute_document_name(self):
        for request in self:
            record = request._record()
            request.document_name = record.display_name if record else self.env._('Deleted record')

    @api.depends('state', 'line_ids.state', 'line_ids.approver_user_ids')
    @api.depends_context('uid')
    def _compute_current(self):
        is_admin = self.env.user.has_group('om_approval.group_approval_manager')
        for request in self:
            line = request._pending_line()
            request.approval_step = line.name
            request.approver_user_ids = line.approver_user_ids
            request.can_approve = bool(line) and (
                self.env.user in line.approver_user_ids - line.approved_user_ids or is_admin)

    @api.depends('state', 'lock_record', 'keep_locked', 'date_unlocked', 'method')
    def _compute_is_locking(self):
        for request in self:
            request.is_locking = request._locks()

    def _locks(self):
        self.ensure_one()
        if not (self.method and self.lock_record):
            return False
        return self.state in ('to_approve', 'approved') or (
            self.state == 'done' and self.keep_locked and not self.date_unlocked)

    @api.model
    def _locking_domain(self, model, ids):
        """ :return: the domain of the requests keeping the records `ids` of `model` read-only """
        return Domain([('res_model', '=', model), ('res_id', 'in', ids), ('method', '!=', False),
                       ('lock_record', '=', True)]) & (
            Domain('state', 'in', ('to_approve', 'approved'))
            | Domain([('state', '=', 'done'), ('keep_locked', '=', True), ('date_unlocked', '=', False)]))

    def _search_approver_user_ids(self, operator, value):
        return [('state', '=', 'to_approve'),
                ('line_ids', 'any', [('state', '=', 'pending'), ('approver_user_ids', operator, value)])]

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    @api.model
    def _request(self, record, flow, method=False, button_name=False, note=False, attachments=None):
        """ Ask for the approval of `record` along `flow`, with the note and the files of the requester.

        :return: the request, already approved when no step applies or when the requester approves them all
        """
        request = self.sudo().create({
            'request_note': note or False,
            'name': self.env['ir.sequence'].sudo().next_by_code('approval.request') or self.env._('New'),
            'flow_id': flow.id or False,
            'res_model': record._name,
            'res_id': record.id,
            'method': method,
            'button_name': button_name,
            'requester_id': self.env.user.id,
            'company_id': self.env['approval.rule']._record_company(record).id,
            'lock_record': bool(method and flow.lock_record),
            'keep_locked': bool(method and flow.lock_record and flow.lock_after == 'keep'),
        })
        if attachments:
            attachments.sudo().write({'res_model': request._name, 'res_id': request.id})
            request.attachment_ids = [Command.set(attachments.ids)]
        request._create_lines(record, flow)
        message = self.env._('Approval asked: %s', request.name)
        if note:
            message = self.env._('Approval asked: %(request)s. %(note)s', request=request.name, note=note)
        request._message_document(message)
        request._next()
        return request

    @api.model
    def _gate_call(self, model, method, args, api=False):
        """ Stop a call of the web client or of an external API to a button waiting for an approval.

        :param args: the positional arguments of the call, the ids first
        :return: the action replacing the call when the button waits for an approval, else None
        """
        if method in NOT_BUTTONS or method.startswith('_') or model not in self.env:
            return None
        if not self.env['approval.rule']._has_button_flows(model, method):
            return None
        ids = args[0] if args else None
        if isinstance(ids, int) and not isinstance(ids, bool):
            ids = [ids]
        if not isinstance(ids, (list, tuple)) or not ids or not all(
                isinstance(i, int) and not isinstance(i, bool) for i in ids):
            return None
        return self._gate_button(model, method, list(ids), api=api)

    @api.model
    def _gate_button(self, model, method, ids, api=False):
        """ Decide whether the button `method` of the records `ids` of `model` may run.

        A record a flow applies to runs once its request for the button is approved; that request is then done.
        The button runs only when all the records may run: otherwise nothing runs, and the click asks for the
        approvals missing, with the note of the requester when the flows ask for one, or reminds that they were
        asked for. `api`: called from an external API, which cannot open the dialog of the note.

        :return: None when the button may run, or the action telling the user why it did not
        """
        flows = self.env['approval.rule']
        records = self.env[model].browse(ids).exists()
        approved, waiting, to_ask = self.browse(), [], []
        for record in records:
            flow = flows._get_flow(record, method)
            if not flow:
                continue
            requests = self.sudo().search([
                ('res_model', '=', model), ('res_id', '=', record.id), ('method', '=', method),
                ('state', 'in', ('to_approve', 'approved')),
            ], order='id desc')
            if requests.filtered(lambda r: r.state == 'approved'):
                approved |= requests.filtered(lambda r: r.state == 'approved')[:1]
            elif requests:
                waiting.append((record, requests[0]))
            else:
                to_ask.append((record, flow))
        if to_ask and not api and any(flow.request_note != 'none' for _record, flow in to_ask):
            return self._ask_action(model, method, to_ask, waiting, records, approved)
        if api and any(flow.request_note == 'required' for _record, flow in to_ask):
            raise UserError(self.env._('%s needs an approval asked with a note: ask for it in Odoo.',
                                       to_ask[0][1].button_id.name or method))
        asked = [(record, self._request(record, flow, method=method, button_name=flow.button_id.name))
                 for record, flow in to_ask]
        # asked and approved at once, e.g. by a requester approving all its steps
        approved |= self.browse([request.id for _record, request in asked if request.state == 'approved'])
        blocked = waiting + [(record, request) for record, request in asked if request.state != 'approved']
        if blocked:
            return self._notify_blocked(blocked, {request for _record, request in asked})
        self._consume(approved)
        return None

    def _consume(self, approved):
        """ The approved requests let their button run now: they are done, their records unlocked for the call. """
        approved.sudo().state = 'done'
        for request in approved:
            record = request._record()
            if record is not None:
                self._release_lock(record)

    @api.model
    def _notify_blocked(self, blocked, new_requests):
        lines = []
        for record, request in blocked:
            line = self.env._('%(record)s: approval asked (%(request)s), waiting for %(step)s.') \
                if request in new_requests else self.env._('%(record)s: still waiting for %(step)s (%(request)s).')
            lines.append(line % {'record': record.display_name, 'request': request.name,
                                 'step': request.approval_step})
        note = blocked[0][1].flow_id.note
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Approval needed'),
                'message': '\n'.join(([note] if note else []) + lines),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _ask_action(self, model, method, to_ask, waiting, records, approved):
        """ :return: the dialog asking the requester's note before the approvals are asked """
        flows = self.env['approval.rule'].browse({flow.id for _record, flow in to_ask})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Ask for Approval'),
            'res_model': 'approval.ask',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_res_model': model,
                'default_method': method,
                'default_res_ids': [record.id for record, _flow in to_ask],
                'default_all_ids': records.ids,
                'default_approved_ids': approved.ids,
                'default_waiting_ids': [request.id for _record, request in waiting],
                'default_note_required': any(flow.request_note == 'required' for flow in flows),
                'default_message': '\n'.join(filter(None, flows.mapped('note'))),
            },
        }

    def _create_lines(self, record, flow):
        """ One line per step of `flow` applying to the record. The approvers are decided now, so that a later
            change, e.g. of a manager, does not move an approval already asked for. """
        self.ensure_one()
        values = []
        for step in flow.step_ids.filtered(lambda s: s._applies_to(record)):
            approvers = step._get_approvers(self, record)
            vals = {'request_id': self.id, 'step_id': step.id, 'sequence': step.sequence, 'name': step.name,
                    'approver_user_ids': approvers.ids, 'required_user_ids': approvers.ids,
                    'approval_mode': step.approval_mode, 'approval_count': step.approval_count}
            if flow.self_approve and self.requester_id in approvers:
                if step.approval_mode == 'any' or len(approvers) == 1:
                    vals.update(state='approved', user_id=self.requester_id.id, date=fields.Datetime.now(),
                                note=self.env._('Approved by the requester, an approver of the step.'))
                else:
                    # the requester counts as one of the approvals the step needs
                    vals['approved_user_ids'] = self.requester_id.ids
            values.append(vals)
        if not flow.step_ids:
            fallback = self._fallback_approvers(flow.fallback_group_id)
            values.append({'request_id': self.id, 'sequence': 10, 'name': self.env._('Approval'),
                           'approver_user_ids': ((fallback - self._excluded_approvers()) or fallback).ids})
        lines = self.env['approval.line'].sudo().create(values)
        for line in lines.filtered(lambda line: line.state == 'waiting' and line.approved_user_ids):
            if line._is_complete():
                line.write({'state': 'approved', 'user_id': self.requester_id.id, 'date': fields.Datetime.now(),
                            'note': self.env._('Approved by the requester, an approver of the step.')})

    def _fallback_approvers(self, group):
        """ The users approving a step finding nobody: `group`, by default the approval administrators. """
        group = group or self.env.ref('om_approval.group_approval_manager')
        return group.all_user_ids.filtered(lambda user: user.active and not user.share)

    def _excluded_approvers(self):
        """ The users who do not approve the request when somebody else can. """
        self.ensure_one()
        return self.requester_id

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def action_approve(self, note=False):
        """ Approve the step waiting, with the note of the approver. A step several people approve waits for the
            others, unless an approval manager approves it. """
        for request in self:
            line = request._check_approver()
            request._check_note('approve', note)
            user = self.env.user
            if not line._approve_by(user):
                request.sudo().activity_feedback([ACTIVITY], user_id=user.id, feedback=self.env._('Approved'))
                request.sudo().message_post(body=self.env._(
                    '%(user)s approved %(step)s (%(done)s of %(needed)s)%(note)s', user=user.name, step=line.name,
                    done=line._approvals_given(), needed=line._approvals_needed(),
                    note=': %s' % note if note else ''), subtype_xmlid='mail.mt_note')
                line.sudo().note = '\n'.join(filter(None, [line.note, '%s: %s' % (user.name, note) if note else ''])) \
                    or False
                continue
            line.sudo().write({'state': 'approved', 'user_id': user.id, 'date': fields.Datetime.now(),
                               'note': '\n'.join(filter(None, [line.note, line._on_behalf_note(), note])) or False})
            request.sudo().activity_feedback([ACTIVITY], feedback=self.env._('Approved'))
            if note:
                request.sudo().message_post(body=self.env._('%(user)s approved %(step)s: %(note)s', user=user.name,
                                                            step=line.name, note=note), subtype_xmlid='mail.mt_note')
            request._next()
        return True

    def _check_note(self, decision, note):
        """ Raise when the flow asks a note for the decision and none is given. """
        self.ensure_one()
        mode = self.flow_id[f'{decision}_note'] if self.flow_id else ('required' if decision == 'refuse' else 'none')
        if mode == 'required' and not (note or '').strip():
            raise UserError(self.env._('Write a note to approve %s.', self.name) if decision == 'approve'
                            else self.env._('Write why %s is refused.', self.name))

    def action_refuse(self, reason=False):
        for request in self:
            line = request._check_approver()
            request._check_note('refuse', reason)
            line.sudo().write({'state': 'refused', 'user_id': self.env.user.id, 'date': fields.Datetime.now(),
                               'note': '\n'.join(filter(None, [line._on_behalf_note(), reason]))})
            request.line_ids.filtered(lambda line: line.state == 'waiting').sudo().state = 'cancel'
            request.sudo().activity_unlink([ACTIVITY])
            request.sudo().state = 'refused'
            message = self.env._('Refused by %(user)s at the step %(step)s: %(reason)s', user=self.env.user.name,
                                 step=line.name, reason=reason or self.env._('no reason given'))
            request.sudo().message_post(body=message, partner_ids=request.requester_id.partner_id.ids)
            request._message_document(message)
            request._call_document('_on_approval_refused')
        return True

    def action_open_refuse(self):
        """ Refuse, in a dialog asking the note when the flow asks for one. """
        self.ensure_one()
        return self._decision_action('refuse')

    def action_open_approve(self):
        """ Approve, in a dialog asking the note when the flow asks for one, else at once. """
        self.ensure_one()
        if (self.flow_id.approve_note if self.flow_id else 'none') == 'none':
            return self.action_approve()
        return self._decision_action('approve')

    def _decision_action(self, decision):
        self.ensure_one()
        self._check_approver()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Approve') if decision == 'approve' else self.env._('Refuse'),
            'res_model': 'approval.decide',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_request_id': self.id, 'default_decision': decision},
        }

    def action_dismiss_refusal(self):
        """ The refusal no longer shows at the top of the record. """
        for request in self.filtered(lambda r: r.state == 'refused'):
            if self.env.user != request.requester_id and not self.env.user.has_group(
                    'om_approval.group_approval_manager'):
                raise UserError(self.env._('Only %s, who asked, dismisses the refusal.', request.requester_id.name))
            request.sudo().refusal_dismissed = True
        return True

    def action_cancel(self):
        """ Withdraw the request. The approvals given so far stay, cancelled. """
        for request in self:
            if request.state not in ('to_approve', 'approved'):
                raise UserError(self.env._('%s can no longer be cancelled.', request.name))
            if self.env.user != request.requester_id and not self.env.user.has_group(
                    'om_approval.group_approval_manager'):
                raise UserError(self.env._('Only %(user)s, who asked, can cancel %(request)s.',
                                           user=request.requester_id.name, request=request.name))
            request.line_ids.filtered(lambda line: line.state in ('waiting', 'pending')).sudo().state = 'cancel'
            request.sudo().activity_unlink([ACTIVITY])
            request.sudo().state = 'cancel'
            request._call_document('_on_approval_cancelled')
        return True

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _pending_line(self):
        self.ensure_one()
        if self.state != 'to_approve':
            return self.env['approval.line']
        return self.line_ids.filtered(lambda line: line.state == 'pending')[:1]

    def _next(self):
        """ Ask the approvers of the next step, or approve the request when no step is left. """
        self.ensure_one()
        lines = self.line_ids.sorted(lambda line: (line.sequence, line.id))
        line = lines.filtered(lambda line: line.state == 'waiting')[:1]
        if line:
            line.sudo().write({'state': 'pending', 'date_pending': fields.Datetime.now()})
            for user in line.approver_user_ids:
                self._schedule_approval(user)
            line._apply_delegations()
            return
        self.sudo().state = 'approved'
        self.sudo().message_post(body=self.env._('Approved.'), partner_ids=self.requester_id.partner_id.ids)
        self._message_document(self.env._('Approved: %s', self.name))
        self._call_document('_on_approval_approved')
        if self.method and self.flow_id.run_on_approval and self.requester_id != self.env.user:
            self._run_button()

    def _schedule_approval(self, user):
        self.ensure_one()
        self.sudo().activity_schedule(ACTIVITY, summary=self.env._('Approve: %s', self.document_name),
                                      user_id=user.id)

    def _run_button(self):
        """ Run the approved button as the requester. A failure, e.g. a record changed meanwhile, leaves the request
            approved, for the requester to click the button again. """
        self.ensure_one()
        record = self._record()
        if not record:
            return
        try:
            with self.env.cr.savepoint():
                self.sudo().state = 'done'
                self._release_lock(record)
                getattr(record.with_user(self.requester_id).with_company(self.company_id or self.env.company),
                        self.method)()
        except Exception as error:  # whatever the button raises is reported to the requester
            _logger.info('om_approval: %s could not run %s on %s: %s', self.name, self.method, record, error)
            self.sudo().message_post(
                body=self.env._('Approved, but %(button)s could not run: %(error)s. Click the button again.',
                                button=self.button_name or self.method, error=error),
                partner_ids=self.requester_id.partner_id.ids)
        finally:
            self._restore_lock(record)

    def _check_approver(self):
        self.ensure_one()
        line = self._pending_line()
        if not line:
            raise UserError(self.env._('%s is not waiting for an approval.', self.name))
        if self.env.user not in line.approver_user_ids and not self.env.user.has_group(
                'om_approval.group_approval_manager'):
            raise UserError(self.env._('You are not an approver of %(request)s at the step %(step)s.',
                                       request=self.name, step=line.name))
        return line

    # ------------------------------------------------------------------
    # Lock
    # ------------------------------------------------------------------

    @api.model
    def _release_lock(self, records):
        """ Let the approved button change `records` until the end of the call running it. """
        self.env.cr.cache.setdefault(RUNNING, set()).update((records._name, res_id) for res_id in records.ids)

    @api.model
    def _restore_lock(self, records=None):
        """ Lock `records` again once their button ran; all the records when none is given. """
        if records is None:
            self.env.cr.cache.pop(RUNNING, None)
        else:
            self.env.cr.cache.get(RUNNING, set()).difference_update((records._name, i) for i in records.ids)

    @api.model
    def _check_lock(self, records, field_names=None):
        """ Raise when a request keeps one of `records` read-only. `field_names`: the fields written, None for a
            deletion. """
        if field_names is not None and not set(field_names) - records._approval_lock_exempt_fields():
            return
        running = self.env.cr.cache.get(RUNNING, ())
        ids = [res_id for res_id in records.ids if (records._name, res_id) not in running]
        if not ids:
            return
        request = self.sudo().search(self._locking_domain(records._name, ids), order='id desc', limit=1)
        if request:
            raise UserError(request._lock_message())

    def _lock_message(self):
        self.ensure_one()
        record = self._record()
        name = record.display_name if record is not None else self.document_name
        if self.state == 'to_approve':
            return self.env._('%(record)s is locked: it waits for the approval %(request)s (%(step)s). Withdraw the '
                              'request to change it.', record=name, request=self.name, step=self.approval_step)
        if self.state == 'approved':
            return self.env._('%(record)s is locked: %(request)s is approved, and it unlocks once %(button)s has '
                              'run.', record=name, request=self.name, button=self.button_name or self.method)
        return self.env._('%(record)s is locked since %(request)s approved it: an approval manager unlocks it.',
                          record=name, request=self.name)

    def action_unlock(self):
        """ Let the record approved be changed again. """
        if not self.env.user.has_group('om_approval.group_approval_manager'):
            raise UserError(self.env._('Only the approval managers unlock an approved record.'))
        for request in self.filtered(lambda r: r.state == 'done' and r.keep_locked and not r.date_unlocked):
            request.sudo().write({'date_unlocked': fields.Datetime.now(), 'unlocked_by_id': self.env.user.id})
            message = self.env._('Unlocked by %(user)s: %(request)s no longer keeps it read-only.',
                                 user=self.env.user.name, request=request.name)
            request.sudo().message_post(body=message, subtype_xmlid='mail.mt_note')
            request._message_document(message)
        return True

    # ------------------------------------------------------------------
    # The record, as its form shows it
    # ------------------------------------------------------------------

    @api.model
    def get_approval_models(self):
        """ :return: the models having a button flow, whose forms show their approvals """
        flows = self.env['approval.rule'].sudo().search([('button_id', '!=', False)])
        return sorted(set(flows.mapped('model')) | set(self.env['approval.rule']._locked_models()))

    @api.model
    def get_record_approvals(self, res_model, res_id):
        """ :return: the approvals of the buttons of a record still open or keeping it locked, for its form """
        empty = {'locked': False, 'requests': []}
        if res_model not in self.env or not res_id:
            return empty
        record = self.env[res_model].browse(res_id).exists()
        if not record:
            return empty
        record.check_access('read')
        requests = self.sudo().search([
            ('res_model', '=', res_model), ('res_id', '=', res_id), ('method', '!=', False),
            ('state', 'in', ('to_approve', 'approved', 'done', 'refused')),
        ], order='id desc')
        # the last request of each button: a refusal shows until it is dismissed or asked again
        latest = {}
        for request in requests:
            latest.setdefault(request.method, request)
        requests = requests.filtered(lambda r: (r.state in ('to_approve', 'approved'))
                                     or (r.state == 'done' and r._locks())
                                     or (r.state == 'refused' and not r.refusal_dismissed
                                         and latest[r.method] == r))
        user = self.env.user
        is_manager = user.has_group('om_approval.group_approval_manager')
        result = []
        for request in requests:
            lines = request.line_ids.sorted(lambda line: (line.sequence, line.id))
            current = request._pending_line()
            readable = is_manager or request.requester_id == user or user in request.line_ids.approver_user_ids
            refused = request.line_ids.filtered(lambda line: line.state == 'refused')[:1]
            flow = request.flow_id
            result.append({
                'id': request.id,
                'name': request.name,
                'button': request.button_name or request.method,
                'state': request.state,
                'request_note': request.request_note or False,
                'attachments': [{'id': attachment.id, 'name': attachment.name}
                                for attachment in request.attachment_ids] if readable else [],
                'approve_note': flow.approve_note if flow else 'none',
                'refuse_note': flow.refuse_note if flow else 'required',
                'refused_by': refused.user_id.name or False,
                'refused_step': refused.name or False,
                'refused_reason': refused.note or False,
                'can_dismiss': request.state == 'refused' and (request.requester_id == user or is_manager),
                'progress': current.progress or False,
                'step': current.name or False,
                'step_index': (list(lines).index(current) + 1) if current else 0,
                'step_count': len(lines),
                'approvers': current.approver_user_ids.mapped('name'),
                'requester': request.requester_id.name,
                'asked': format_datetime(self.env, request.create_date, dt_format='short'),
                'locking': request._locks(),
                'keep_locked': request.keep_locked,
                'can_approve': request.state == 'to_approve' and bool(current) and (
                    user in current.approver_user_ids - current.approved_user_ids or is_manager),
                'can_withdraw': request.state in ('to_approve', 'approved') and (
                    request.requester_id == user or is_manager),
                'can_unlock': request.state == 'done' and is_manager,
                'can_open': readable,
                'lines': [{
                    'name': line.name,
                    'state': line.state,
                    'state_label': dict(line._fields['state']._description_selection(self.env)).get(line.state),
                    'approvers': line.approver_user_ids.mapped('name'),
                    'approved': line.approved_user_ids.mapped('name'),
                    'progress': line.progress or False,
                    'user': line.user_id.name or False,
                    'date': format_datetime(self.env, line.date, dt_format='short') if line.date else False,
                    'note': line.note or False,
                } for line in lines] if readable else [],
            })
        return {'locked': any(item['locking'] for item in result), 'requests': result}

    # ------------------------------------------------------------------
    # The record
    # ------------------------------------------------------------------

    def _record(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists() or None

    def _call_document(self, hook):
        """ Tell a document with an approval of its own about the decision. """
        record = self._record()
        if record is not None and not self.method and hasattr(record, hook):
            getattr(record, hook)(self)

    def _message_document(self, body):
        record = self._record()
        if record is not None and hasattr(record, 'message_post'):
            record.message_post(body=body, subtype_xmlid='mail.mt_note')


class ApprovalLine(models.Model):
    """ One step of a request, and its decision. """
    _name = 'approval.line'
    _description = 'Approval'
    _order = 'request_id, sequence, id'

    request_id = fields.Many2one('approval.request', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)
    step_id = fields.Many2one('approval.step', ondelete='set null')
    sequence = fields.Integer()
    name = fields.Char(string='Approval', required=True)
    approver_user_ids = fields.Many2many('res.users', string='Approvers')
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('pending', 'To Approve'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancel', 'Cancelled'),
    ], required=True, default='waiting', index=True)
    user_id = fields.Many2one('res.users', string='Decided By')
    date = fields.Datetime(string='Decided On')
    note = fields.Text()
    date_pending = fields.Datetime(string='Asked On', readonly=True)
    substitutes = fields.Json(readonly=True, help='The substitutes added, by user id: the names they stand for.')
    date_reminded = fields.Datetime(string='Reminded On', readonly=True)
    date_escalated = fields.Datetime(string='Escalated On', readonly=True)
    approval_mode = fields.Selection([('any', 'Any One of Them'), ('all', 'All of Them'),
                                      ('count', 'A Number of Them')], default='any', required=True, readonly=True)
    approval_count = fields.Integer(readonly=True)
    required_user_ids = fields.Many2many('res.users', 'approval_line_required_user_rel', string='Asked',
                                         readonly=True, help='The approvers the step asked first.')
    approved_user_ids = fields.Many2many('res.users', 'approval_line_approved_user_rel', string='Approved By',
                                         readonly=True)
    progress = fields.Char(compute='_compute_progress', help='How many approved, of how many needed.')

    @api.depends('approval_mode', 'approved_user_ids', 'required_user_ids', 'approver_user_ids', 'state')
    def _compute_progress(self):
        for line in self:
            line.progress = '%s / %s' % (line._approvals_given(), line._approvals_needed()) \
                if line.approval_mode != 'any' and line.state == 'pending' else False

    # ------------------------------------------------------------------
    # Several approvers
    # ------------------------------------------------------------------

    def _approvals_needed(self):
        self.ensure_one()
        if self.approval_mode == 'all':
            return len(self.required_user_ids or self.approver_user_ids)
        if self.approval_mode == 'count':
            return min(self.approval_count or 1, len(self.approver_user_ids) or 1)
        return 1

    def _approvals_given(self):
        self.ensure_one()
        return len(self.approved_user_ids)

    def _is_complete(self):
        """ :return: whether the step has the approvals it needs """
        self.ensure_one()
        approved = self.approved_user_ids
        if self.approval_mode == 'count':
            return len(approved) >= self._approvals_needed()
        if self.approval_mode == 'all':
            missing = (self.required_user_ids or self.approver_user_ids) - approved
            if missing:
                # a substitute approving stands for the approvers away
                found = self.env['approval.delegation']._substitutes(missing, self.request_id.flow_id)
                for delegate, stands_for in found.items():
                    if delegate in approved:
                        missing -= stands_for
            return not missing
        return bool(approved)

    def _approve_by(self, user):
        """ Count the approval of `user`. :return: whether the step is approved now """
        self.ensure_one()
        if self.approval_mode == 'any' or user not in self.approver_user_ids:
            # one approver decides, or an approval manager decides for the step
            return True
        if self.approval_mode == 'all' and user not in self.required_user_ids and not self.env[
                'approval.delegation']._substitutes(self.required_user_ids, self.request_id.flow_id).get(user):
            # asked by an escalation: decides for the step
            return True
        self.sudo().approved_user_ids = [Command.link(user.id)]
        return self._is_complete()

    # ------------------------------------------------------------------
    # Substitutes and escalation
    # ------------------------------------------------------------------

    def _add_approvers(self, users, message):
        """ Let `users` decide the step too: they get the activity, the request says why. """
        self.ensure_one()
        request = self.request_id
        if not request.flow_id.self_approve:
            users -= request._excluded_approvers()
        users -= self.approver_user_ids
        if not users:
            return users
        self.sudo().approver_user_ids = [(4, user.id) for user in users]
        for user in users:
            request._schedule_approval(user)
        request.sudo().message_post(body=message, subtype_xmlid='mail.mt_note', partner_ids=users.partner_id.ids)
        return users

    def _apply_delegations(self):
        """ Add the substitutes of the approvers away today. """
        Delegation = self.env['approval.delegation']
        for line in self.filtered(lambda line: line.state == 'pending'):
            found = Delegation._substitutes(line.approver_user_ids, line.request_id.flow_id)
            substitutes = dict(line.substitutes or {})
            for delegate, stands_for in found.items():
                message = self.env._('%(delegate)s approves %(step)s for %(users)s, away.', delegate=delegate.name,
                                     step=line.name, users=', '.join(stands_for.mapped('name')))
                if line._add_approvers(delegate, message):
                    substitutes[str(delegate.id)] = stands_for.mapped('name')
            if substitutes != (line.substitutes or {}):
                line.sudo().substitutes = substitutes

    def _on_behalf_note(self):
        """ :return: the note of a decision taken by a substitute """
        self.ensure_one()
        names = (self.substitutes or {}).get(str(self.env.user.id))
        return self.env._('On behalf of %s.', ', '.join(names)) if names else False

    @api.model
    def _cron_follow_up(self):
        """ Every day: the substitutes of the approvers away from today, the reminders, the escalations. """
        lines = self.sudo().search([('state', '=', 'pending'), ('request_id.state', '=', 'to_approve')])
        lines._apply_delegations()
        now = fields.Datetime.now()
        for line in lines.filtered('step_id'):
            step = line.step_id
            asked = line.date_pending or line.create_date
            if step.escalate_days and not line.date_escalated and asked <= now - timedelta(days=step.escalate_days):
                users = step._escalation_users(line)
                line._add_approvers(users, self.env._('%(step)s is waiting since %(days)s days: %(users)s asked to '
                                                      'decide too.', step=line.name, days=step.escalate_days,
                                                      users=', '.join(users.mapped('name'))))
                line.sudo().date_escalated = now
            elif step.remind_days and (line.date_reminded or asked) <= now - timedelta(days=step.remind_days):
                line.request_id.sudo().message_post(
                    body=self.env._('Reminder: %(step)s is waiting for your decision.', step=line.name),
                    subtype_xmlid='mail.mt_note', partner_ids=line.approver_user_ids.partner_id.ids)
                line.sudo().date_reminded = now
