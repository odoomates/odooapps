from odoo import api, fields, models
from odoo.exceptions import UserError


class ApprovalMixin(models.AbstractModel):
    """ A document with an approval of its own: it is submitted, then approved in steps along its flow.

    A model inheriting the mixin reacts to the decisions in ``_on_approval_approved``, ``_on_approval_refused``,
    ``_on_approval_cancelled`` and ``_on_approval_reset``. Without a flow, the approval administrators approve it.
    """
    _name = 'approval.mixin'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Approval Mixin'

    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancel', 'Cancelled'),
    ], string='Approval', required=True, default='draft', copy=False, index=True, tracking=True)
    approval_request_ids = fields.One2many(
        'approval.request', 'res_id', string='Approval Requests', copy=False,
        domain=lambda self: [('res_model', '=', self._name), ('method', '=', False)])
    approval_request_id = fields.Many2one('approval.request', compute='_compute_approval_request')
    approval_line_ids = fields.One2many('approval.line', string='Approvals', compute='_compute_approval_request')
    approval_step = fields.Char(string='Waiting For', compute='_compute_approval_request')
    approver_user_ids = fields.Many2many(
        'res.users', string='Approvers', compute='_compute_approval_request', search='_search_approver_user_ids')
    can_approve = fields.Boolean(compute='_compute_approval_request')

    @api.depends('approval_state', 'approval_request_ids.state', 'approval_request_ids.line_ids.state')
    @api.depends_context('uid')
    def _compute_approval_request(self):
        for document in self:
            # read as the super user: the request only fills fields of a document the user already reads, e.g. an
            # employee on the portal following their loan
            request = document._approval_current_request().sudo()
            document.approval_request_id = request
            document.approval_line_ids = request.line_ids
            document.approval_step = request.approval_step
            document.approver_user_ids = request.approver_user_ids
            document.can_approve = request.can_approve

    def _search_approver_user_ids(self, operator, value):
        return [('approval_request_ids', 'any', [('approver_user_ids', operator, value)])]

    def _approval_current_request(self):
        self.ensure_one()
        if not self.id:
            return self.env['approval.request']
        return self.env['approval.request'].sudo().search(
            [('res_model', '=', self._name), ('res_id', '=', self.id), ('method', '=', False)],
            order='id desc', limit=1).sudo(False)

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def _on_approval_submitted(self, request):
        pass

    def _on_approval_approved(self, request):
        self.sudo().approval_state = 'approved'

    def _on_approval_refused(self, request):
        self.sudo().approval_state = 'refused'

    def _on_approval_cancelled(self, request):
        self.sudo().approval_state = 'cancel'

    def _on_approval_reset(self):
        pass

    def _approval_check_requester(self):
        """ Raise unless the current user may submit, withdraw or reset the document. """

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_approval_submit(self):
        for document in self:
            if document.approval_state != 'draft':
                raise UserError(self.env._('Only a draft can be submitted: %s is not.', document.display_name))
            document._approval_check_requester()
        for document in self:
            flow = self.env['approval.rule']._get_flow(document)
            document.sudo().approval_state = 'to_approve'
            request = self.env['approval.request']._request(document, flow)
            if request.state == 'to_approve':
                document._on_approval_submitted(request)
        return True

    def action_approval_approve(self):
        for document in self:
            document._approval_pending_request().action_approve()
        return True

    def action_approval_open_approve(self):
        """ Approve, in a dialog asking the note when the flow asks for one. Several documents are approved at
            once, without a note, unless a note is required. """
        if len(self) == 1:
            return self._approval_pending_request().action_open_approve()
        for document in self:
            request = document._approval_pending_request()
            if request.flow_id.approve_note == 'required':
                raise UserError(self.env._('%s needs a note to be approved: approve it on its own.',
                                           document.display_name))
            request.action_approve()
        return True

    def action_approval_refuse(self, reason=False):
        for document in self:
            document._approval_pending_request().action_refuse(reason)
        return True

    def action_approval_open_refuse(self):
        self.ensure_one()
        return self._approval_pending_request().action_open_refuse()

    def action_approval_reset(self):
        """ Back to draft, from a refusal, a cancellation or while waiting. The approvals given so far stay in the
            history of the request, cancelled. """
        for document in self:
            if document.approval_state not in ('to_approve', 'refused', 'cancel'):
                raise UserError(self.env._('%s cannot be set back to draft.', document.display_name))
            document._approval_check_requester()
            request = document._approval_current_request()
            if request.state == 'to_approve':
                request.sudo().action_cancel()
            document.sudo().approval_state = 'draft'
            document._on_approval_reset()
        return True

    def action_approval_cancel(self):
        for document in self:
            if document.approval_state not in ('draft', 'to_approve'):
                raise UserError(self.env._('%s can no longer be cancelled.', document.display_name))
            document._approval_check_requester()
            request = document._approval_current_request()
            if request.state == 'to_approve':
                request.sudo().action_cancel()
            document.sudo().approval_state = 'cancel'
        return True

    def _approval_pending_request(self):
        self.ensure_one()
        request = self._approval_current_request()
        if self.approval_state != 'to_approve' or request.state != 'to_approve':
            raise UserError(self.env._('%s is not waiting for an approval.', self.display_name))
        return request
