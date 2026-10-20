from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IrActionsServer(models.Model):
    """ Send WhatsApp: a server action that sends a template, for automation
    rules (an order confirmed, an invoice posted...), contextual actions and
    scheduled actions. """
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('mail_post',), ('om_whatsapp', 'Send WhatsApp')], ondelete={'om_whatsapp': 'cascade'})
    om_whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', 'WhatsApp Template', compute='_compute_om_whatsapp_template_id',
        ondelete='set null', readonly=False, store=True, domain="[('model_id', '=', model_id)]")
    om_whatsapp_account_id = fields.Many2one(
        'om.whatsapp.account', 'WhatsApp Account', ondelete='set null',
        help="The account to send from. Empty: the one of the template, else the one of the user who triggers it.")

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

    @api.constrains('state', 'model_id', 'om_whatsapp_template_id')
    def _check_om_whatsapp_model(self):
        for action in self.filtered(lambda a: a.state == 'om_whatsapp'):
            if action.model_id.transient or not action.model_id.is_mail_thread:
                raise ValidationError(_("A WhatsApp is sent from a document with a chatter."))
            if action.om_whatsapp_template_id and action.om_whatsapp_template_id.model_id != action.model_id:
                raise ValidationError(_("The WhatsApp template of %(action)s is not for this model.", action=action.name))

    def _run_action_om_whatsapp_multi(self, eval_context=None):
        if not self.om_whatsapp_template_id or self._is_recompute():
            return False
        records = eval_context.get('records') or eval_context.get('record')
        if records:
            records._message_om_whatsapp_template(self.om_whatsapp_template_id, account=self.om_whatsapp_account_id)
        return False
