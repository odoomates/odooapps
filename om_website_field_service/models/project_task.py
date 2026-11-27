from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import plaintext2html
from odoo.tools.mimetypes import guess_mimetype

PREFERRED_TIMES = [
    ('any', "Any time"),
    ('morning', "Morning"),
    ('afternoon', "Afternoon"),
]


class ProjectTask(models.Model):
    _inherit = 'project.task'

    fs_online_request = fields.Boolean(string="Requested Online", copy=False, readonly=True)
    fs_to_review = fields.Boolean(
        string="Request to Review", copy=False, index=True,
        help="Online request waiting for a dispatcher: accept it to plan it.")
    fs_preferred_date = fields.Date(string="Preferred Date", copy=False)
    fs_preferred_date_to = fields.Date(string="Preferred Until", copy=False)
    fs_preferred_time = fields.Selection(PREFERRED_TIMES, string="Preferred Time", copy=False)

    def action_fs_accept_request(self):
        self.write({'fs_to_review': False})
        return True

    def action_fs_reject_request(self):
        self.filtered('fs_to_review').write({'fs_to_review': False})
        return self.action_fs_cancel()

    # ------------------------------------------------------------------
    # Online request
    # ------------------------------------------------------------------

    @api.model
    def _fs_request_project(self, company):
        project = company.fs_request_project_id
        if not project:
            project = self.env['project.project'].sudo().search(
                [('is_field_service', '=', True), ('company_id', 'in', [company.id, False])], limit=1)
        if not project:
            raise UserError(self.env._("Online requests are not available: there is no field service project."))
        return project

    @api.model
    def _fs_create_online_request(self, partner, site, values, photos=None):
        """ Create the job of a service request sent from the website (sudo environment).

        :param partner: customer
        :param site: address of the site
        :param dict values: ``name``, ``description``, ``equipment``, ``serial``,
            ``preferred_date``, ``preferred_date_to``, ``preferred_time``
        :param list photos: (file name, content) of the pictures sent
        """
        company = self.env.company
        description = plaintext2html(values.get('description') or '')
        equipment = '\n'.join(filter(None, [
            values.get('equipment'),
            values.get('serial') and self.env._("Serial number: %s", values['serial']),
        ]))
        job_values = {
            'name': values.get('name') or self.env._("Service request"),
            'project_id': self._fs_request_project(company).id,
            'partner_id': partner.id,
            'site_partner_id': site.id,
            'partner_phone': values.get('phone') or partner.phone or False,
            'description': description,
            'site_equipment': equipment or False,
            'fs_online_request': True,
            'fs_to_review': company.fs_request_review,
            'fs_preferred_date': values.get('preferred_date') or False,
            'fs_preferred_date_to': values.get('preferred_date_to') or False,
            'fs_preferred_time': values.get('preferred_time') or False,
            'company_id': company.id,
        }
        job_values.update(self._fs_online_request_equipment(partner, values))
        job = self.with_context(mail_create_nolog=True, om_fs_job=True).create(job_values)
        job.message_subscribe(partner_ids=partner.ids)
        # pictures only
        pictures = [(name, content) for name, content in photos or []
                    if guess_mimetype(content or b'').startswith('image/')]
        job.message_post(
            body=Markup('<p>%s</p>') % self.env._("Service request sent from the website."),
            attachments=pictures,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
            author_id=partner.id,
        )
        return job

    @api.model
    def _fs_online_request_equipment(self, partner, values):
        """ The equipment of the customer with the serial number given, when the equipment of the
        sites is recorded (field service stock). """
        serial = (values.get('serial') or '').strip()
        if not serial or 'om.fs.equipment' not in self.env:
            return {}
        equipment = self.env['om.fs.equipment'].search([
            ('commercial_partner_id', '=', partner.commercial_partner_id.id),
            ('lot_id.name', '=ilike', serial),
        ], limit=1)
        return {'equipment_id': equipment.id} if equipment else {}

    @api.model
    def _fs_find_or_create_site(self, partner, address):
        """ The address of the site: one of the customer, or a new delivery address. """
        commercial = partner.commercial_partner_id
        street = (address.get('street') or '').strip()
        if not street:
            return partner
        candidates = self.env['res.partner'].search([('id', 'child_of', commercial.id)])
        for candidate in candidates:
            if (candidate.street or '').strip().lower() == street.lower() and \
                    (candidate.city or '').strip().lower() == (address.get('city') or '').strip().lower():
                return candidate
        if not (partner.street or partner.city) and partner == commercial:
            partner.write({key: value for key, value in address.items() if value})
            return partner
        return self.env['res.partner'].create({
            'type': 'delivery',
            'parent_id': commercial.id,
            'name': address.get('site_name') or False,
            **{key: value for key, value in address.items() if key != 'site_name' and value},
        })

    @api.model
    def _fs_find_or_create_partner(self, name, email, phone):
        email = (email or '').strip()
        partner = self.env['res.partner']
        if email:
            partner = partner.search([('email', '=ilike', email)], limit=1)
        if not partner:
            partner = partner.create({'name': name or email, 'email': email or False, 'phone': phone or False})
        elif phone and not partner.phone:
            partner.phone = phone
        return partner

    def _fs_portal_status(self):
        """ Status shown to the customer in the portal. """
        self.ensure_one()
        if self.fs_to_review or (self.job_state == 'new' and not self.planned_start):
            return self.env._("Waiting for planning")
        return dict(self._fields['job_state']._description_selection(self.env))[self.job_state]
