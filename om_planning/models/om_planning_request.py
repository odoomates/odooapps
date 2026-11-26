from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class OmPlanningRequest(models.Model):
    _name = 'om.planning.request'
    _description = "Planning Request"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(compute='_compute_name', string="Name")
    request_type = fields.Selection([
        ('claim', 'Claim an open slot'),
        ('switch', 'Switch with someone'),
        ('unassign', 'Leave the slot'),
    ], string="Request", required=True, default='claim', tracking=True)
    slot_id = fields.Many2one('om.planning.slot', string="Slot", required=True, ondelete='cascade', index=True)
    slot_start = fields.Datetime(related='slot_id.start_datetime', string="Slot Start")
    slot_end = fields.Datetime(related='slot_id.end_datetime', string="Slot End")
    role_id = fields.Many2one(related='slot_id.role_id', string="Slot Role")
    resource_id = fields.Many2one('resource.resource', string="Requested By", required=True, index=True)
    target_resource_id = fields.Many2one(
        'resource.resource', string="Switch With",
        help="Person who takes the slot.")
    reason = fields.Text(string="Reason")
    state = fields.Selection([
        ('pending', 'To Approve'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='pending', required=True, tracking=True)
    approver_id = fields.Many2one('res.users', string="Decided By", readonly=True)
    can_approve = fields.Boolean(compute='_compute_can_approve', string="Can Approve")
    company_id = fields.Many2one(related='slot_id.company_id', store=True, string="Company")

    @api.depends('request_type', 'resource_id', 'slot_id')
    def _compute_name(self):
        types = dict(self._fields['request_type']._description_selection(self.env))
        for request in self:
            request.name = f"{types.get(request.request_type, '')}: {request.resource_id.name or ''}"

    @api.depends_context('uid')
    def _compute_can_approve(self):
        for request in self:
            request.can_approve = request.state == 'pending' and self.env.user in request._planning_approvers()

    def _planning_approvers(self):
        """ Users who can approve the request (planning managers, plus the manager of the
        person in the people bridge). """
        self.ensure_one()
        return self.env.ref('om_planning.group_planning_manager').sudo().all_user_ids.filtered(
            lambda u: not u.share and self.company_id in u.company_ids)

    @api.constrains('request_type', 'target_resource_id', 'slot_id', 'resource_id')
    def _check_request(self):
        for request in self:
            if request.request_type == 'switch' and not request.target_resource_id:
                raise UserError(self.env._("Choose the person who takes the slot."))
            if request.request_type == 'claim' and not request.slot_id.is_open:
                raise UserError(self.env._("Only open slots can be claimed."))
            if request.request_type in ('switch', 'unassign') and request.resource_id not in request.slot_id.resource_ids:
                raise UserError(self.env._("%s is not planned on this slot.", request.resource_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('resource_id'):
                resource = self.env['resource.resource'].search([('user_id', '=', self.env.uid)], limit=1)
                if resource:
                    vals['resource_id'] = resource.id
        requests = super().create(vals_list)
        for request in requests:
            duplicate = self.sudo().search_count([
                ('id', '!=', request.id), ('slot_id', '=', request.slot_id.id),
                ('resource_id', '=', request.resource_id.id), ('request_type', '=', request.request_type),
                ('state', '=', 'pending'),
            ])
            if duplicate:
                raise UserError(self.env._("You already asked this for this slot."))
            request.sudo()._planning_notify_approvers()
        return requests

    def _planning_notify_approvers(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for request in self:
            for user in request._planning_approvers()[:5]:
                request.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary=self.env._("Approve the planning request"),
                    note=request.slot_id._planning_short_label(request.resource_id),
                    user_id=user.id,
                )

    def _check_can_approve(self):
        for request in self:
            if request.state != 'pending':
                raise UserError(self.env._("This request is already decided."))
            if not self.env.su and self.env.user not in request._planning_approvers():
                raise UserError(self.env._("You cannot approve or refuse this request."))

    def action_approve(self):
        self._check_can_approve()
        for request in self.sudo():
            # the people concerned are notified of the decision: the slot stays published
            slot = request.slot_id.with_context(om_planning_keep_published=True)
            if request.request_type == 'claim':
                if not slot.is_open:
                    raise UserError(self.env._("The slot %s is already taken.", slot.display_name))
                slot.write({'resource_ids': [Command.link(request.resource_id.id)]})
            elif request.request_type == 'switch':
                slot.write({'resource_ids': [Command.unlink(request.resource_id.id),
                                             Command.link(request.target_resource_id.id)]})
            else:
                slot.write({'resource_ids': [Command.unlink(request.resource_id.id)]})
            request.write({'state': 'approved', 'approver_id': self.env.uid})
            request.activity_feedback(['mail.mail_activity_data_todo'])
            # other pending claims of the same slot are refused
            if request.request_type == 'claim':
                others = self.sudo().search([('slot_id', '=', slot.id), ('request_type', '=', 'claim'),
                                             ('state', '=', 'pending'), ('id', '!=', request.id)])
                others.write({'state': 'refused', 'approver_id': self.env.uid})
                others.activity_unlink(['mail.mail_activity_data_todo'])
            request._planning_notify_requester()
        return True

    def action_refuse(self):
        self._check_can_approve()
        for request in self.sudo():
            request.write({'state': 'refused', 'approver_id': self.env.uid})
            request.activity_unlink(['mail.mail_activity_data_todo'])
            request._planning_notify_requester()
        return True

    def action_cancel(self):
        for request in self:
            if request.state != 'pending':
                raise UserError(self.env._("Only pending requests can be cancelled."))
        self.write({'state': 'cancelled'})
        self.sudo().activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def _planning_notify_requester(self):
        states = dict(self._fields['state']._description_selection(self.env))
        for request in self:
            partners = request.resource_id._planning_get_partner()
            if request.request_type == 'switch' and request.state == 'approved':
                partners |= request.target_resource_id._planning_get_partner()
            if partners:
                request.message_notify(
                    partner_ids=partners.ids,
                    subject=self.env._("Planning request %s", states[request.state].lower()),
                    body=self.env._("The request \"%(request)s\" for %(slot)s was %(state)s.",
                                    request=request.name,
                                    slot=request.slot_id._planning_short_label(request.resource_id),
                                    state=states[request.state].lower()),
                )
