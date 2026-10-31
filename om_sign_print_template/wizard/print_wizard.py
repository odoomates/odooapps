from odoo import api, fields, models
from odoo.exceptions import UserError


class PrintWizard(models.TransientModel):
    _inherit = 'print.wizard'

    has_sign_roles = fields.Boolean(compute='_compute_has_sign_roles')

    @api.depends('template_id.sign_role_ids')
    def _compute_has_sign_roles(self):
        for wizard in self:
            wizard.has_sign_roles = bool(wizard.template_id.sign_role_ids)

    def action_issue_sign(self):
        """ Issue the print and open its signature request, to check the signers before sending it. """
        if len(self.res_ids or []) != 1:
            raise UserError(self.env._('Send one record at a time for signature.'))
        issues = self._create_drafts()
        issues.action_issue()
        return issues.action_request_signature()
