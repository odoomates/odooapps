import re

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

LOW_CONFIDENCE = 0.7
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
INSTRUCTIONS = """Read this CV (resume). Give the contact details of the candidate as printed, the highest degree
from the allowed values, the date the candidate can start if written, the tags from the allowed values that fit,
a two-sentence summary, the jobs (most recent first), the education, the skills and the languages."""


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    om_ai_read_state = fields.Selection([
        ('done', 'Read by AI'),
        ('to_check', 'Read by AI, To Check'),
    ], string='AI Reading', copy=False, readonly=True)
    om_ai_read_notes = fields.Text(string='AI Notes', copy=False, readonly=True)

    def _om_ai_cv(self):
        self.ensure_one()
        Extract = self.env['om.ai.extract']
        attachments = self.message_main_attachment_id | self.attachment_ids.sorted('id', reverse=True)
        return attachments.filtered(lambda a: a.mimetype == 'application/pdf' or Extract._is_image(a.mimetype, a.name)
                                    or (a.mimetype or '').startswith('text/'))[:1]

    def _om_ai_schema(self):
        Extract = self.env['om.ai.extract']
        degrees = self.env['hr.recruitment.degree'].search([]).mapped('name')
        tags = self.env['hr.applicant.category'].search([], limit=100).mapped('name')
        degree = {'type': ['string', 'null'], 'description': 'Highest degree'}
        if degrees:
            degree['enum'] = degrees + [None]
        tag_items = {'type': 'string'}
        if tags:
            tag_items['enum'] = tags
        text_list = {'type': 'array', 'items': {'type': 'string'}}
        properties = {
            'name': {'type': ['string', 'null']},
            'email': {'type': ['string', 'null']},
            'phone': {'type': ['string', 'null']},
            'linkedin': {'type': ['string', 'null'], 'description': 'LinkedIn profile URL'},
            'degree': degree,
            'available_from': {'type': ['string', 'null'], 'format': 'date'},
            'tags': {'type': 'array', 'items': tag_items},
            'summary': {'type': ['string', 'null']},
            'experience': dict(text_list, description='One line per job: title, company, years'),
            'education': dict(text_list, description='One line per degree: degree, school, year'),
            'skills': text_list,
            'languages': text_list,
        }
        return Extract._schema(properties, required=list(properties))

    def action_om_ai_read_cv(self):
        for applicant in self:
            attachment = applicant._om_ai_cv()
            if not attachment:
                raise UserError(self.env._('Attach the CV (a PDF, an image or a text file) first.'))
            applicant._om_ai_read(attachment)
        if len(self) == 1:
            return True
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'message': self.env._('%s CV(s) read.', len(self)), 'type': 'success',
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def _om_ai_read(self, attachment):
        self.ensure_one()
        Extract = self.env['om.ai.extract']
        data, problems, _payload = Extract._extract(attachment.raw, attachment.mimetype, attachment.name,
                                                    self._om_ai_schema(), instructions=INSTRUCTIONS)
        checks = []
        values = {}
        if data.get('name') and not self.partner_name:
            values['partner_name'] = data['name']
        email = (data.get('email') or '').strip()
        if email:
            if not EMAIL_RE.match(email):
                checks.append(self.env._('The email read does not look valid: %s', email))
            elif not self.email_from:
                values['email_from'] = email
            elif self.email_from.lower() != email.lower():
                checks.append(self.env._('The CV gives another email: %s', email))
        if data.get('phone') and not self.partner_phone:
            values['partner_phone'] = data['phone']
        linkedin = data.get('linkedin') or ''
        if linkedin and not self.linkedin_profile:
            values['linkedin_profile'] = linkedin if linkedin.startswith('http') else 'https://' + linkedin
        if data.get('degree') and not self.type_id:
            degree = self.env['hr.recruitment.degree'].search([('name', '=', data['degree'])], limit=1)
            if degree:
                values['type_id'] = degree.id
        if data.get('available_from') and not self.availability:
            values['availability'] = data['available_from']
        tags = self.env['hr.applicant.category'].search([('name', 'in', data.get('tags') or [])])
        if tags - self.categ_ids:
            values['categ_ids'] = [Command.link(tag.id) for tag in tags - self.categ_ids]
        notes = self._om_ai_notes_html(data)
        if notes:
            values['applicant_notes'] = (self.applicant_notes or Markup('')) + notes
        if not data.get('name'):
            checks.append(self.env._('No name was read.'))
        if not email and not data.get('phone'):
            checks.append(self.env._('No email and no phone were read.'))
        if data.get('confidence') is not None and data['confidence'] < LOW_CONFIDENCE:
            checks.append(self.env._('The AI is not sure of this reading.'))
        all_notes = list(data['flags']) + problems + checks
        values.update({
            'om_ai_read_state': 'to_check' if all_notes else 'done',
            'om_ai_read_notes': '\n'.join(all_notes) or False,
        })
        self.write(values)
        self.message_post(body=Extract._summary_html(data, problems, checks))

    def _om_ai_notes_html(self, data):
        sections = [
            (self.env._('Summary'), [data['summary']] if data.get('summary') else []),
            (self.env._('Experience'), data.get('experience') or []),
            (self.env._('Education'), data.get('education') or []),
            (self.env._('Skills'), [', '.join(data['skills'])] if data.get('skills') else []),
            (self.env._('Languages'), [', '.join(data['languages'])] if data.get('languages') else []),
        ]
        parts = []
        for title, items in sections:
            items = [item for item in items if item]
            if not items:
                continue
            if len(items) == 1:
                parts.append(Markup('<p><strong>%s:</strong> %s</p>') % (title, items[0]))
            else:
                parts.append(Markup('<p><strong>%s</strong></p><ul>%s</ul>') % (
                    title, Markup('').join(Markup('<li>%s</li>') % item for item in items)))
        if not parts:
            return Markup('')
        return Markup('<h4>%s</h4>') % self.env._('Read from the CV by the AI') + Markup('').join(parts)
