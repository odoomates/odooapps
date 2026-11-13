from ast import literal_eval

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmWhatsappComposer(models.TransientModel):
    """ Send a WhatsApp message from one or several documents. One document
    gets an editable number and text; several documents get the template
    rendered for each of them, at the number found on each document. """
    _name = 'om.whatsapp.composer'
    _description = 'Send WhatsApp'

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
        'om.whatsapp.account', required=True, default=lambda self: self.env['om.whatsapp.account']._get_default_account(),
        domain="[('user_ids', 'in', uid)]")
    can_send_files = fields.Boolean(related='account_id.can_send_files')
    template_id = fields.Many2one(
        'om.whatsapp.template', string='Template',
        domain="[('model', '=', res_model), ('account_id', 'in', [False, account_id])]")
    partner_id = fields.Many2one('res.partner', compute='_compute_recipient', store=True, readonly=False)
    number = fields.Char(compute='_compute_recipient', store=True, readonly=False)
    body = fields.Text('Message', compute='_compute_body', store=True, readonly=False)
    attach_report = fields.Boolean(compute='_compute_attach_report', store=True, readonly=False)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    use_exclusion_list = fields.Boolean(
        'Skip Opted-out Numbers', default=True,
        help="Do not send to the numbers of the phone blacklist.")
    recipient_valid_count = fields.Integer(compute='_compute_recipient_counts')
    recipient_invalid_count = fields.Integer(compute='_compute_recipient_counts')

    @api.depends('res_ids')
    def _compute_res_count(self):
        for composer in self:
            composer.res_count = len(composer._get_res_ids())

    @api.depends('res_model', 'res_ids')
    @api.depends_context('om_whatsapp_number')
    def _compute_recipient(self):
        """ The number of the record, or the one given in the context by the
        WhatsApp button of a phone field. """
        for composer in self:
            records = composer._get_records()
            if len(records) != 1:
                composer.partner_id = False
                composer.number = False
                continue
            info = records._phone_get_recipients_info()[records.id]
            composer.partner_id = info['partner'][:1] if info['partner'] else False
            composer.number = self.env.context.get('om_whatsapp_number') or info['sanitized'] or info['number']

    @api.depends('res_model', 'res_ids')
    def _compute_recipient_counts(self):
        for composer in self:
            records = composer._get_records()
            info = records._phone_get_recipients_info() if len(records) > 1 else {}
            composer.recipient_valid_count = len([1 for values in info.values() if values['sanitized']])
            composer.recipient_invalid_count = len(info) - composer.recipient_valid_count

    @api.depends('template_id', 'res_ids')
    def _compute_body(self):
        for composer in self:
            template = composer.template_id
            res_ids = composer._get_res_ids()
            if not template:
                composer.body = composer.body or False
            elif len(res_ids) == 1:
                composer.body = template._om_whatsapp_render_body(res_ids)[res_ids[0]]
            else:
                composer.body = template.body

    @api.depends('template_id')
    def _compute_attach_report(self):
        for composer in self:
            composer.attach_report = bool(composer.template_id.report_id)

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

    def action_send(self):
        self.ensure_one()
        records = self._get_records()
        if not records:
            raise UserError(_("There is no document to send from."))
        if not self.body and not self.template_id:
            raise UserError(_("Write a message or pick a template."))
        messages = self._post_messages(records)
        notifications = messages._om_whatsapp_notifications()
        queued = notifications.filtered(lambda n: n.notification_status == 'ready')
        action = queued._om_whatsapp_send() if queued else None
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
                'message': _("%(queued)s WhatsApp message(s) sent, %(skipped)s skipped.", queued=len(queued), skipped=skipped),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _post_messages(self, records):
        """ Post the message on each document, or on its contact when the
        document has no chatter. """
        single = len(records) == 1
        if single:
            number = records._phone_format(number=self.number) or self.number
            info = {records.id: {'partner': self.partner_id, 'sanitized': number, 'number': self.number}}
            bodies = {records.id: self.body}
        else:
            info = records._phone_get_recipients_info()
            bodies = (self.template_id._om_whatsapp_render_body(records.ids) if self.template_id
                      else dict.fromkeys(records.ids, self.body))
        numbers = [values['sanitized'] for values in info.values() if values['sanitized']]
        opted_out = set()
        if self.use_exclusion_list and numbers:
            opted_out = set(self.env['phone.blacklist'].sudo().search([('number', 'in', numbers)]).mapped('number'))

        messages = self.env['mail.message']
        for record in records:
            values = info[record.id]
            partner = values['partner'][:1] if values['partner'] else self.env['res.partner']
            document = record if hasattr(record, 'message_post') else partner
            if not document:
                raise UserError(_("%(record)s has no chatter and no contact to log the message on.", record=record.display_name))
            failure = {}
            attachment_ids = []
            if not values['sanitized']:
                failure = {'failure_type': 'om_whatsapp_number', 'failure_reason': _("No valid number")}
            elif values['sanitized'] in opted_out:
                failure = {'failure_type': 'om_whatsapp_optout', 'failure_reason': _("Number is opted out")}
            elif self.can_send_files:
                attachment_ids = self._prepare_attachments(record, single)
            messages |= document._message_om_whatsapp(
                self.account_id, bodies[record.id], values['sanitized'] or values['number'] or False,
                partner=partner, attachment_ids=attachment_ids, om_whatsapp_template_id=self.template_id.id or False,
                **failure)
        return messages

    def _prepare_attachments(self, record, single):
        attachments = self.env['ir.attachment']
        if single and self.attachment_ids:
            uploaded = self.attachment_ids.filtered(lambda a: a.res_model == self._name)
            uploaded.sudo().write({'res_model': record._name, 'res_id': record.id})
            attachments |= self.attachment_ids
        if self.attach_report and (report := self.template_id._om_whatsapp_render_report(record.id)):
            name, content = report
            attachments |= self.env['ir.attachment'].create({
                'name': name,
                'raw': content,
                'res_model': record._name,
                'res_id': record.id,
            })
        return attachments.ids
