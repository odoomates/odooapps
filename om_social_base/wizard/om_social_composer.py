from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmSocialComposer(models.TransientModel):
    """ Send a message from one or several documents, from an account of the
    Social Inbox. It goes to the customer of each document (the contact, or
    the contact of the document), at their identity in the channel of the
    account. Channel modules extend it: how they find the address of a
    document, what they offer besides the text. """
    _name = 'om.social.composer'
    _description = 'Send a Message'

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        context = self.env.context
        res_model = res.get('res_model') or context.get('active_model')
        res_ids = context.get('active_ids') or (context.get('active_id') and [context['active_id']]) or []
        if not res.get('res_ids') and res_ids:
            res['res_ids'] = repr(res_ids)
        res['res_model'] = res_model
        return res

    res_model = fields.Char('Document Model', required=True)
    res_ids = fields.Char('Document IDs', required=True)
    res_count = fields.Integer(compute='_compute_res_count')
    account_id = fields.Many2one(
        'om.social.account', required=True, default=lambda self: self._default_account(),
        domain="[('user_ids', 'in', uid)]")
    can_send_files = fields.Boolean(related='account_id.can_send_files')
    partner_id = fields.Many2one('res.partner', compute='_compute_partner_id', store=True, readonly=False)
    address = fields.Char(compute='_compute_address', store=True, readonly=False,
                          help="The address of the customer in the channel of the account.")
    body = fields.Text('Message')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    @api.model
    def _default_account(self):
        return self.env['om.social.account']._get_default_account()

    @api.depends('res_ids')
    def _compute_res_count(self):
        for composer in self:
            composer.res_count = len(composer._get_res_ids())

    @api.depends('res_model', 'res_ids')
    def _compute_partner_id(self):
        for composer in self:
            records = composer._get_records()
            composer.partner_id = composer._get_partner(records) if len(records) == 1 else False

    @api.depends('partner_id', 'account_id')
    def _compute_address(self):
        for composer in self:
            composer.address = composer._get_address(composer.partner_id) if composer.res_count == 1 else False

    @api.model
    def _get_partner(self, record):
        """ The customer of a document: the contact itself, else its contact. """
        if record._name == 'res.partner':
            return record
        return record.partner_id if 'partner_id' in record._fields and record._fields['partner_id'].type == 'many2one' \
            else self.env['res.partner']

    def _get_address(self, partner):
        """ Where a message to ``partner`` goes from the account: their
        identity in its channel, its address, else its user ID. """
        self.ensure_one()
        identity = partner.sudo().om_social_identity_ids.filtered(lambda i: i.channel == self.account_id.channel)[:1]
        if not identity:
            return False
        if identity.address:
            return identity.address
        return identity.user_ref if self.account_id.can_send_user_ref else False

    def _get_res_ids(self):
        self.ensure_one()
        return literal_eval(self.res_ids) if self.res_ids else []

    def _get_records(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return self.env['res.partner']
        return self.env[self.res_model].browse(self._get_res_ids()).exists()

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _check_content(self):
        if not self.body:
            raise UserError(_("Write a message."))

    def action_send(self):
        self.ensure_one()
        records = self._get_records()
        if not records:
            raise UserError(_("There is no document to send from."))
        self._check_content()
        messages = self._post_messages(records)
        notifications = messages._om_social_notifications()
        queued = notifications.filtered(lambda n: n.notification_status == 'ready')
        action = queued._om_social_send() if queued else None
        if action:
            return action
        skipped = len(notifications) - len(queued)
        if len(notifications) == 1 and skipped:
            raise UserError(_("Not sent: %(reason)s", reason=notifications.failure_reason))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning' if skipped else 'success',
                'message': _("%(queued)s message(s) sent, %(skipped)s skipped.", queued=len(queued), skipped=skipped),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _post_messages(self, records):
        """ Post the message on each document, or on its contact when the
        document has no chatter. """
        single = len(records) == 1
        messages = self.env['mail.message']
        for record in records:
            partner = self.partner_id if single else self._get_partner(record)
            document = record if hasattr(record, 'message_post') else partner
            if not document:
                raise UserError(_("%(record)s has no chatter and no contact to log the message on.",
                                  record=record.display_name))
            address = self.address if single else self._get_address(partner)
            failure = {} if address else {'failure_type': 'om_social_error',
                                          'failure_reason': _("No address in this channel")}
            attachment_ids = self._prepare_attachments(record, single) if address and self.can_send_files else []
            messages |= document._message_om_social(
                self.account_id, self.body, address or False, partner=partner, attachment_ids=attachment_ids,
                **failure)
        return messages

    def _prepare_attachments(self, record, single):
        attachments = self.env['ir.attachment']
        if single and self.attachment_ids:
            uploaded = self.attachment_ids.filtered(lambda a: a.res_model == self._name)
            uploaded.sudo().write({'res_model': record._name, 'res_id': record.id})
            attachments |= self.attachment_ids
        return attachments.ids
