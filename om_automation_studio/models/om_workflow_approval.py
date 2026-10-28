from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import ormcache
from odoo.tools.misc import format_datetime

# what an approver may change on their own approval
APPROVER_FIELDS = {'comment'}


class OmWorkflowApproval(models.Model):
    """ A question an Approval step asks one user about a record. The
    approver finds it as an activity; their answer sends the run on by the
    Approved or Rejected exit. """
    _name = 'om.workflow.approval'
    _description = 'Workflow Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, readonly=True)
    run_id = fields.Many2one('om.workflow.run', required=True, ondelete='cascade', index=True, readonly=True)
    workflow_id = fields.Many2one(related='run_id.workflow_id', store=True)
    node_key = fields.Char(readonly=True)
    res_model = fields.Char(related='run_id.res_model', store=True, index=True)
    res_id = fields.Many2oneReference(related='run_id.res_id', store=True, index=True)
    res_name = fields.Char(related='run_id.res_name', string='Record')
    user_id = fields.Many2one('res.users', string='Approver', required=True, readonly=True, index=True)
    note = fields.Html(readonly=True)
    state = fields.Selection([
        ('pending', 'To Approve'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, readonly=True, index=True, tracking=True)
    comment = fields.Text()
    deadline = fields.Datetime(readonly=True)
    decided_by_id = fields.Many2one('res.users', string='Answered By', readonly=True)
    decided_on = fields.Datetime('Answered On', readonly=True)
    can_decide = fields.Boolean(compute='_compute_can_decide')
    # while pending, these fields of the record cannot change (none listed: no field can)
    lock = fields.Boolean('Blocks the Record', readonly=True)
    lock_fields = fields.Json(readonly=True)
    # administrators may answer for the approver, unless the step forbids it
    approver_only = fields.Boolean('Only the Approver Answers', readonly=True)

    @api.depends_context('uid')
    @api.depends('user_id', 'state', 'approver_only')
    def _compute_can_decide(self):
        for approval in self:
            approval.can_decide = approval.state == 'pending' and approval._may_answer(self.env.user)

    def _may_answer(self, user):
        return self.user_id == user or (not self.approver_only and user.has_group('base.group_system'))

    @api.model_create_multi
    def create(self, vals_list):
        approvals = super().create(vals_list)
        if approvals.filtered('lock'):
            self.env.registry.clear_caches()
        for approval in approvals:
            approval.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=approval.name,
                user_id=approval.user_id.id,
                date_deadline=approval.deadline and approval.deadline.date(),
            )
        return approvals

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('base.group_system') and set(vals) - APPROVER_FIELDS:
            raise AccessError(_("Approvals are answered with the Approve and Reject buttons."))
        return super().write(vals)

    def action_approve(self):
        return self._decide('approved')

    def action_reject(self):
        return self._decide('rejected')

    def action_open_record(self):
        self.ensure_one()
        return self.run_id.sudo().action_open_record()

    def _decide(self, state):
        for approval in self:
            if not approval.can_decide:
                raise UserError(_("Only %s can answer this approval.", approval.user_id.name))
        user = self.env.user
        for approval in self.sudo():
            approval.write({'decided_by_id': user.id, 'decided_on': fields.Datetime.now()})
            approval._close(state)
            record = approval.run_id._record()
            label = _("Approved") if state == 'approved' else _("Rejected")
            message = f"{label}: {approval.comment}" if approval.comment else label
            if record is not None and 'message_ids' in record._fields:
                record.message_post(
                    body=self._answered_by(label, user, approval) + (f"\n{approval.comment}" if approval.comment else ''),
                    subtype_xmlid='mail.mt_note',
                )
            if user != approval.user_id:
                approval._tell_approver(label, user)
            approval.run_id._resume(state, message)
        return True

    def _tell_approver(self, label, user):
        """ Someone else answered: say so to the approver. """
        self.message_post(
            body=_("%(answer)s by %(user)s on your behalf.", answer=label, user=user.name),
            partner_ids=self.user_id.partner_id.ids,
            subtype_xmlid='mail.mt_comment',
        )

    def _answered_by(self, label, user, approval):
        if user == approval.user_id:
            return _("%(answer)s by %(user)s: %(name)s", answer=label, user=user.name, name=approval.name)
        return _("%(answer)s by %(user)s on behalf of %(approver)s: %(name)s", answer=label,
                          user=user.name, approver=approval.user_id.name, name=approval.name)

    def _close(self, state):
        """ Set the answer and close the activity of the approver. """
        if self.filtered('lock'):
            self.env.registry.clear_caches()
        self.sudo().write({'state': state})
        self.activity_ids.sudo().action_feedback(feedback=_("Answered: %s", state))

    # ------------------------------------------------------------------
    # the record waiting for the answer
    # ------------------------------------------------------------------

    @api.model
    @ormcache()
    def _locked_models(self):
        """ The models with a record that a pending approval blocks. """
        return frozenset(group['res_model'] for group in self.sudo()._read_group(
            [('state', '=', 'pending'), ('lock', '=', True)], ['res_model'], ['res_model']))

    @api.model
    def _check_lock(self, records, vals):
        """ Refuse to change ``vals`` on ``records`` while an approval that
        blocks them waits for its answer. """
        approvals = self.sudo().search([
            ('res_model', '=', records._name), ('res_id', 'in', records.ids),
            ('state', '=', 'pending'), ('lock', '=', True),
        ])
        for approval in approvals._still_needed():
            locked = set(approval.lock_fields or vals)
            changed = [name for name in vals if name in locked]
            if not changed:
                continue
            labels = [records._fields[name]._description_string(self.env)
                      for name in changed if name in records._fields]
            raise UserError(_(
                "%(record)s waits for approval by %(user)s (%(question)s): %(fields)s cannot change until "
                "it is answered.",
                record=approval.res_name, user=approval.user_id.name, question=approval.name,
                fields=', '.join(labels),
            ))

    @api.model
    @ormcache()
    def _approval_models(self):
        """ The models a published workflow asks approvals about. """
        models_ = set()
        for workflow in self.env['om.workflow'].sudo().search([('state', '=', 'active')]):
            if any(node.get('type') == 'approval' for node in (workflow.version_id.graph or {}).get('nodes', [])):
                models_.add(workflow.model)
        return frozenset(models_)

    @api.model
    def get_approval_models(self):
        """ For the banner of the forms: the models to ask about. """
        return sorted(self._approval_models())

    @api.model
    def get_pending(self, res_model, res_id):
        """ The approvals the record ``res_id`` of ``res_model`` waits for, as
        the banner of its form shows them. """
        if res_model not in self._approval_models() or res_model not in self.env:
            return []
        record = self.env[res_model].browse(res_id).exists()
        if not record:
            return []
        record.check_access_rights('read')
        record.check_access_rule('read')
        approvals = self.sudo().search([('res_model', '=', res_model), ('res_id', '=', res_id),
                                        ('state', '=', 'pending')])._still_needed()
        result = []
        for approval in approvals:
            names = approval.lock_fields or []
            result.append({
                'id': approval.id,
                'name': approval.name,
                'user': approval.user_id.name,
                'asked': format_datetime(self.env, approval.create_date),
                'deadline': (approval.deadline and format_datetime(self.env, approval.deadline)) or '',
                'can_decide': approval._may_answer(self.env.user),
                'on_behalf': approval.user_id != self.env.user,
                'lock': approval.lock,
                # the approver may not see the record, and answers from the Approvals menu
                'approver_can_read': self._can_read(record.with_user(approval.user_id)),
                'locked': [record._fields[name]._description_string(self.env)
                           for name in names if name in record._fields],
            })
        return result

    @api.model
    def _can_read(self, record):
        try:
            record.check_access_rights('read')
            record.check_access_rule('read')
        except AccessError:
            return False
        return True

    def _still_needed(self):
        """ The approvals whose record does not meet the stop condition of
        their workflow; the runs of the others stop at once. """
        needed = self.browse()
        for approval in self:
            run = approval.run_id
            record = run._record()
            stop_domain = run._stop_domain()
            if record is not None and stop_domain and record.filtered_domain(stop_domain):
                run._stop('done', _("Stopped: the stop condition is met."))
            else:
                needed |= approval
        return needed

    def _post_asked(self, record):
        """ Tell on the record who its approval waits for. """
        self.ensure_one()
        if 'message_ids' not in record._fields:
            return
        body = Markup(_("Waiting for approval by %(user)s: %(link)s")) % {
            'user': self.user_id.name,
            'link': Markup('<a href="#" data-oe-model="%s" data-oe-id="%s">%s</a>') % (self._name, self.id, self.name),
        }
        record.message_post(body=body, subtype_xmlid='mail.mt_note')
