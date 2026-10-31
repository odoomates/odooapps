from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.binary import BinaryBytes


class SignRequest(models.Model):
    """ An issued print sent for signature: its signers come from the roles of its template, and the signed PDF is
    the print with the signatures at their placeholders. """
    _inherit = 'sign.request'

    issue_id = fields.Many2one('print.issue', string='Issued Print', ondelete='restrict', index='btree_not_null',
                               readonly=True, check_company=True)

    @api.model
    def _create_for_issue(self, issue):
        """ :return: a draft request to sign the issued print, its signers found from the roles of its template """
        issue.ensure_one()
        if issue.state != 'issued':
            raise UserError(self.env._('Issue %s before sending it for signature.', issue.name))
        template = issue.template_id
        record = issue._get_record()
        signers = [Command.create({
            'sequence': role.sequence,
            'role_name': role.name,
            'partner_id': (role._get_partner(record) if record else role.partner_id).id,
        }) for role in template.sign_role_ids]
        return self.create({
            'name': issue.subject or template.name,
            'issue_id': issue.id,
            'res_model': issue.res_model,
            'res_id': issue.res_id,
            'email_code': template.sign_email_code,
            'reminder_days': template.sign_reminder_days,
            'date_deadline': fields.Date.context_today(self) + timedelta(days=template.sign_validity_days)
                if template.sign_validity_days else False,
            'signer_ids': signers,
            'company_id': issue.company_id.id,
        })

    def _get_document(self):
        self.ensure_one()
        if self.state == 'draft' and self.issue_id:
            raw = self.issue_id.attachment_id.sudo().raw
            return raw.content if raw else b''
        return super()._get_document()

    def _check_document(self, document):
        # the print is a PDF, except in the tests, where Odoo renders the reports as HTML
        if self.issue_id:
            return None
        return super()._check_document(document)

    def _sent_document_values(self, document):
        self.ensure_one()
        if self.issue_id:
            return {'document_file': BinaryBytes(document), 'document_filename': self.issue_id.attachment_id.name}
        return super()._sent_document_values(document)

    def _build_signed_document(self):
        """ The print itself, with the signatures at their placeholders, and below the text for the others. """
        self.ensure_one()
        if self.issue_id and not self.sign_template_id:
            return self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'om_sign_print_template.action_report_sign_document', res_ids=self.ids)[0]
        return super()._build_signed_document()

    def _get_open_record(self):
        self.ensure_one()
        return self.issue_id or super()._get_open_record()
