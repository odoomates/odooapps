from odoo import _, api, fields, models


class IrActionsServer(models.Model):
    """ Send WhatsApp: a server action that sends a template, for automation
    rules (an order confirmed, an invoice posted...), contextual actions and
    scheduled actions. """
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('log_note',), ('om_whatsapp', 'Send WhatsApp')], ondelete={'om_whatsapp': 'cascade'})
    om_whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', 'WhatsApp Template', compute='_compute_om_whatsapp_template_id',
        ondelete='set null', readonly=False, store=True, domain="[('model_id', '=', model_id)]")
    om_whatsapp_account_id = fields.Many2one(
        'om.whatsapp.account', 'WhatsApp Account', ondelete='set null',
        help="The account to send from. Empty: the one of the template, else the one of the user who triggers it.")

    def _name_depends(self):
        return [*super()._name_depends(), 'om_whatsapp_template_id']

    def _generate_action_name(self):
        self.ensure_one()
        if self.state == 'om_whatsapp' and self.om_whatsapp_template_id:
            return _('Send WhatsApp %(template_name)s', template_name=self.om_whatsapp_template_id.name)
        return super()._generate_action_name()

    @api.depends('state')
    def _compute_available_model_ids(self):
        whatsapp = self.filtered(lambda action: action.state == 'om_whatsapp')
        if whatsapp:
            models = self.env['ir.model'].search([('is_mail_thread', '=', True), ('transient', '=', False)])
            for action in whatsapp:
                action.available_model_ids = models.ids
        super(IrActionsServer, self - whatsapp)._compute_available_model_ids()

    @api.depends('model_id', 'state')
    def _compute_om_whatsapp_template_id(self):
        self.filtered(
            lambda a: a.state != 'om_whatsapp' or a.model_id != a.om_whatsapp_template_id.model_id
        ).om_whatsapp_template_id = False

    @api.model
    def _warning_depends(self):
        return super()._warning_depends() + ['om_whatsapp_template_id']

    def _get_warning_messages(self):
        self.ensure_one()
        warnings = super()._get_warning_messages()
        if self.state == 'om_whatsapp':
            if self.model_id.transient or not self.model_id.is_mail_thread:
                warnings.append(_("A WhatsApp is sent from a document with a chatter."))
            if self.om_whatsapp_template_id and self.om_whatsapp_template_id.model_id != self.model_id:
                warnings.append(_("The WhatsApp template of %(action)s is not for this model.", action=self.name))
        return warnings

    def _run_action_om_whatsapp_multi(self, eval_context=None):
        if not self.om_whatsapp_template_id or self._is_recompute():
            return False
        records = eval_context.get('records') or eval_context.get('record')
        if records:
            records._message_om_whatsapp_template(self.om_whatsapp_template_id, account=self.om_whatsapp_account_id)
        return False
