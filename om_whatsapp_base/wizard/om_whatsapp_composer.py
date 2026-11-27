from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmWhatsappComposer(models.TransientModel):
    """ Send a WhatsApp message from one or several documents. One document
    gets an editable number and text; several documents get the template
    rendered for each of them, at the number found on each document. """
    _name = 'om.whatsapp.composer'
    _inherit = ['om.social.composer']
    _description = 'Send WhatsApp'

    account_id = fields.Many2one(domain="[('user_ids', 'in', uid), ('channel', '=', 'whatsapp')]")
    can_send_user_id = fields.Boolean(related='account_id.can_send_user_ref')
    template_id = fields.Many2one(
        'om.whatsapp.template', string='Template',
        domain="[('model', '=', res_model), ('account_id', 'in', [False, account_id])]")
    partner_id = fields.Many2one(compute='_compute_recipient')
    number = fields.Char(compute='_compute_recipient', store=True, readonly=False)
    om_whatsapp_user_id = fields.Char(
        'WhatsApp User ID', compute='_compute_recipient', store=True,
        help="The contact has no number: the message goes to the id WhatsApp gives them for your business.")
    body = fields.Text(compute='_compute_body', store=True, readonly=False)
    attach_report = fields.Boolean(compute='_compute_attach_report', store=True, readonly=False)
    use_exclusion_list = fields.Boolean(
        'Skip Opted-out Numbers', default=True,
        help="Do not send to the numbers of the phone blacklist.")
    recipient_valid_count = fields.Integer(compute='_compute_recipient_counts')
    recipient_invalid_count = fields.Integer(compute='_compute_recipient_counts')

    @api.model
    def _default_account(self):
        return self.env['om.social.account']._get_default_account('whatsapp')

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
                composer.om_whatsapp_user_id = False
                continue
            info = records._phone_get_recipients_info()[records.id]
            composer.partner_id = info['partner'][:1] if info['partner'] else False
            composer.number = self.env.context.get('om_whatsapp_number') or info['sanitized'] or info['number']
            composer.om_whatsapp_user_id = composer._get_user_id(composer.partner_id)

    def _compute_address(self):
        """ The number of the composer is the address. """
        for composer in self:
            composer.address = False

    @api.depends('res_model', 'res_ids', 'account_id')
    def _compute_recipient_counts(self):
        for composer in self:
            records = composer._get_records()
            info = records._phone_get_recipients_info() if len(records) > 1 else {}
            composer.recipient_valid_count = len([1 for values in info.values() if values['sanitized'] or (
                composer.can_send_user_id and composer._get_user_id(values['partner']))])
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

    @api.model
    def _get_user_id(self, partners):
        """ The WhatsApp user ID of the contact, for one without a number. """
        identity = partners[:1].sudo().om_social_identity_ids.filtered(
            lambda i: i.channel == 'whatsapp' and i.user_ref)[:1] if partners else False
        return identity.user_ref if identity else False

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _check_content(self):
        if not self.body and not self.template_id:
            raise UserError(_("Write a message or pick a template."))

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
            # without a number, the WhatsApp user ID of the contact, for a provider that sends to it
            user_id = not values['sanitized'] and self.can_send_user_id \
                and (self.om_whatsapp_user_id if single else self._get_user_id(partner))
            if not values['sanitized'] and not user_id:
                failure = {'failure_type': 'om_whatsapp_number', 'failure_reason': _("No valid number")}
            elif values['sanitized'] in opted_out:
                failure = {'failure_type': 'om_whatsapp_optout', 'failure_reason': _("Number is opted out")}
            elif self.can_send_files:
                attachment_ids = self._prepare_attachments(record, single)
            messages |= document._message_om_whatsapp(
                self.account_id, bodies[record.id], values['sanitized'] or values['number'] or False,
                partner=partner, attachment_ids=attachment_ids, om_whatsapp_template_id=self.template_id.id or False,
                om_whatsapp_user_id=user_id or False, **failure)
        return messages

    def _prepare_attachments(self, record, single):
        attachment_ids = super()._prepare_attachments(record, single)
        if self.attach_report and (report := self.template_id._om_whatsapp_render_report(record.id)):
            name, content = report
            attachment_ids.append(self.env['ir.attachment'].create({
                'name': name,
                'raw': content,
                'res_model': record._name,
                'res_id': record.id,
            }).id)
        return attachment_ids
