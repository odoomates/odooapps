from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import clean_context

# above this number of requests sent in bulk, they are sent in the background
BULK_NOW = 20


class SignSend(models.TransientModel):
    """ Send a sign template: who signs as each of its roles, and how. In bulk, one request per contact chosen for
    one of its roles, the others signed by the same people. """
    _name = 'sign.send'
    _description = 'Send a Sign Template'

    template_id = fields.Many2one('sign.template', required=True, ondelete='cascade')
    name = fields.Char(string='Document', required=True, compute='_compute_from_template', store=True,
                       readonly=False, precompute=True)
    line_ids = fields.One2many('sign.send.line', 'wizard_id', string='Signers', compute='_compute_from_template',
                               store=True, readonly=False, precompute=True)
    message = fields.Text(compute='_compute_from_template', store=True, readonly=False, precompute=True,
                          help='Shown to the signers in the email and on the signing page.')
    date_deadline = fields.Date(string='Sign By', compute='_compute_from_template', store=True, readonly=False,
                                precompute=True)
    reminder_days = fields.Integer(string='Remind Every', compute='_compute_from_template', store=True,
                                   readonly=False, precompute=True,
                                   help='Days between the reminders to a signer. 0 for no reminder.')
    email_code = fields.Boolean(compute='_compute_from_template', store=True, readonly=False, precompute=True,
                                help='Each signer gets a code by email and enters it before signing.')
    cc_partner_ids = fields.Many2many(
        'res.partner', 'sign_send_cc_partner_rel', 'wizard_id', 'partner_id', string='Copy To',
        compute='_compute_from_template', store=True, readonly=False, precompute=True,
        help='These contacts do not sign: they are told when it is sent, and get the signed PDF.')
    cc_notify_sent = fields.Boolean(string='Tell Them When Sent', compute='_compute_from_template', store=True,
                                    readonly=False, precompute=True,
                                    help='The copy recipients get an email when the document is sent for '
                                         'signature, not only once it is signed.')
    bulk = fields.Boolean(string='In Bulk', readonly=True)
    bulk_role_id = fields.Many2one(
        'sign.template.role', string='One Request per Contact For', compute='_compute_bulk_role_id', store=True,
        readonly=False, precompute=True, domain="[('template_id', '=', template_id)]",
        help='The role signed by each contact below, in a request of their own; the other roles are signed by the '
             'same people in every request.')
    bulk_partner_ids = fields.Many2many('res.partner', 'sign_send_bulk_partner_rel', 'wizard_id', 'partner_id',
                                        string='Contacts')
    bulk_count = fields.Integer(compute='_compute_bulk_count', string='Requests')

    @api.depends('template_id')
    def _compute_from_template(self):
        for wizard in self:
            template = wizard.template_id
            defaults = template._request_defaults()
            wizard.name = template.name
            wizard.message = defaults['message']
            wizard.date_deadline = defaults['date_deadline']
            wizard.reminder_days = defaults['reminder_days']
            wizard.email_code = defaults['email_code']
            wizard.cc_partner_ids = template.cc_partner_ids
            wizard.cc_notify_sent = defaults['cc_notify_sent']
            wizard.line_ids = [Command.clear()] + [Command.create({
                'role_id': role.id,
                'partner_id': role._get_partner().id,
            }) for role in template.role_ids]

    @api.depends('template_id', 'bulk')
    def _compute_bulk_role_id(self):
        for wizard in self:
            roles = wizard.template_id.role_ids
            wizard.bulk_role_id = (roles.filtered(lambda role: role.signer_type == 'choose') or roles)[:1] \
                if wizard.bulk else False

    @api.depends('bulk_partner_ids')
    def _compute_bulk_count(self):
        for wizard in self:
            wizard.bulk_count = len(wizard.bulk_partner_ids)

    def _request_values(self):
        """ :return: the values of the requests sent, but their signers """
        self.ensure_one()
        return {
            'name': self.name,
            'message': self.message,
            'date_deadline': self.date_deadline,
            'reminder_days': self.reminder_days,
            'email_code': self.email_code,
            'cc_partner_ids': [Command.set(self.cc_partner_ids.ids)],
            'cc_notify_sent': self.cc_notify_sent,
        }

    def _prepare_request(self):
        """ :return: the values of the request sent """
        self.ensure_one()
        partners = {line.role_id: line.partner_id for line in self.line_ids}
        return self.template_id._prepare_request(partners, **self._request_values())

    def _check_lines(self, lines):
        missing = lines.filtered(lambda line: not line.partner_id)
        if missing:
            raise UserError(self.env._('Choose who signs as %s.', missing[0].role_id.name))
        if self.template_id.role_ids - self.line_ids.role_id:
            raise UserError(self.env._('The roles of %s changed: send it again.', self.template_id.name))

    def action_send(self):
        self.ensure_one()
        if self.bulk:
            return self.action_send_bulk()
        self._check_lines(self.line_ids)
        # the defaults of the wizard are not those of the request
        request = self.env['sign.request'].with_context(clean_context(self.env.context)).create(
            self._prepare_request())
        request.action_send()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def _check_bulk(self):
        """ :raise UserError: when the contacts cannot each get a request """
        self.ensure_one()
        role, partners = self.bulk_role_id, self.bulk_partner_ids
        if not role or role.template_id != self.template_id:
            raise UserError(self.env._('Choose the role each contact signs as.'))
        if not partners:
            raise UserError(self.env._('Choose the contacts to send %s to.', self.template_id.name))
        no_email = partners.filtered(lambda partner: not partner.email_normalized)
        if no_email:
            raise UserError(self.env._('These contacts have no email address to receive the request: %s.',
                                       ', '.join(no_email.mapped('display_name'))))
        seen = {}
        for partner in partners:
            other = seen.setdefault(partner.email_normalized, partner)
            if other != partner:
                raise UserError(self.env._('%(one)s and %(other)s have the same email address: choose one of them.',
                                           one=other.display_name, other=partner.display_name))
        self._check_lines(self.line_ids.filtered(lambda line: line.role_id != role))

    def action_send_bulk(self):
        """ One request per contact, sent now when they are a few, else in the background.

        :return: a notification of how many were sent or queued, then the list of the requests """
        self.ensure_one()
        self._check_bulk()
        template, role = self.template_id, self.bulk_role_id
        fixed = {line.role_id: line.partner_id for line in self.line_ids if line.role_id != role}
        queued = len(self.bulk_partner_ids) > BULK_NOW
        values = {**self._request_values(), 'source': 'bulk', 'send_queued': queued}
        vals_list = [template._prepare_request({**fixed, role: partner}, **{
            **values, 'name': '%s - %s' % (template.name, partner.name)}) for partner in self.bulk_partner_ids]
        requests = self.env['sign.request'].with_context(clean_context(self.env.context)).create(vals_list)
        if queued:
            self.env.ref('om_sign.ir_cron_sign_send_queued')._trigger()
            message = self.env._('%s requests are queued: they are sent in the background.', len(requests))
        else:
            requests.action_send()
            message = self.env._('%s requests are sent.', len(requests))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': message,
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': self.env._('%s: Sent in Bulk', template.name),
                    'res_model': 'sign.request',
                    'view_mode': 'list,form',
                    'views': [(False, 'list'), (False, 'form')],
                    'domain': [('id', 'in', requests.ids)],
                    'context': {'create': False},
                },
            },
        }


class SignSendLine(models.TransientModel):
    _name = 'sign.send.line'
    _description = 'Signer of a Sign Template Sent'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('sign.send', required=True, ondelete='cascade')
    role_id = fields.Many2one('sign.template.role', required=True, ondelete='cascade')
    sequence = fields.Integer(related='role_id.sequence')
    partner_id = fields.Many2one('res.partner', string='Signer')
    email = fields.Char(related='partner_id.email')
    varied = fields.Boolean(compute='_compute_varied', string='Each Contact',
                            help='In bulk, each contact chosen signs as this role, in a request of their own.')

    @api.depends('wizard_id.bulk', 'wizard_id.bulk_role_id', 'role_id')
    def _compute_varied(self):
        for line in self:
            line.varied = line.wizard_id.bulk and line.role_id == line.wizard_id.bulk_role_id
