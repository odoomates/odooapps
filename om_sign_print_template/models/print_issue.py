import re

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

# where a signature goes in the text of a template, e.g. [signature: Employee]
PLACEHOLDER = re.compile(r'\[\s*signature\s*:\s*([^\]<]+?)\s*\]', re.IGNORECASE)


class PrintIssue(models.Model):
    _inherit = 'print.issue'

    sign_request_ids = fields.One2many('sign.request', 'issue_id', string='Signature Requests')
    sign_request_count = fields.Integer(compute='_compute_sign_request_count', string='Signatures')
    has_sign_roles = fields.Boolean(compute='_compute_has_sign_roles')

    @api.depends('sign_request_ids')
    def _compute_sign_request_count(self):
        for issue in self:
            issue.sign_request_count = len(issue.sign_request_ids)

    @api.depends('template_id.sign_role_ids')
    def _compute_has_sign_roles(self):
        for issue in self:
            issue.has_sign_roles = bool(issue.template_id.sign_role_ids)

    def _sign_body(self, sign_request=None):
        """ :return: the text of the print with the signature blocks at their placeholders, blank before it is
                     signed, and the blocks of the signers without a placeholder, to print below the text """
        self.ensure_one()
        Request = self.env['sign.request']
        signers = sign_request.signer_ids if sign_request else None
        placed = self.env['sign.request.signer']

        def replace(match):
            nonlocal placed
            role = match.group(1).strip()
            if signers is None:
                return str(Request._render_signature_blocks([{'role': role}]))
            found = signers.filtered(lambda signer: (signer.role_name or '').strip().lower() == role.lower())
            if not found:
                return match.group(0)
            placed |= found
            return str(Request._render_signature_blocks(Request._signer_entries(found)))

        body = PLACEHOLDER.sub(replace, str(self.body_html or ''))
        others = Request._signer_entries(signers - placed) if signers is not None else []
        return Markup(body), others

    def action_request_signature(self):
        self.ensure_one()
        if not self.template_id.sign_role_ids:
            raise UserError(self.env._('Add the signers to the template %s first.', self.template_id.name))
        request = self.env['sign.request']._create_for_issue(self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_open_sign_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Signatures'),
            'res_model': 'sign.request',
            'view_mode': 'list,form',
            'domain': [('issue_id', '=', self.id)],
            'context': {'create': False},
        }
