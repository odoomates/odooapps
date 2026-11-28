from odoo import fields, http
from odoo.http import request
from odoo.tools import email_normalize

from odoo.addons.om_website_field_service.models.project_task import PREFERRED_TIMES

MAX_PHOTOS = 5
MAX_PHOTO_SIZE = 10 * 1024 * 1024


class WebsiteFieldService(http.Controller):

    def _fs_request_values(self, errors=None, values=None):
        user = request.env.user
        partner = user.partner_id
        sites = request.env['res.partner']
        if not user._is_public():
            commercial = partner.commercial_partner_id
            sites = request.env['res.partner'].sudo().search(
                [('id', 'child_of', commercial.id), ('street', '!=', False)], order='type desc, id')
        return {
            'errors': errors or {},
            'values': values or ({} if user._is_public() else {
                'contact_name': partner.name,
                'email': partner.email,
                'phone': partner.phone,
            }),
            'sites': sites,
            'countries': request.env['res.country'].sudo().search([]),
            'default_country': request.env.company.country_id,
            'preferred_times': PREFERRED_TIMES,
            'today': fields.Date.to_string(fields.Date.context_today(request.env.user)),
            'is_public': user._is_public(),
        }

    @http.route(['/field-service/request'], type='http', auth='public', website=True, sitemap=True)
    def fs_request_form(self, **kw):
        return request.render('om_website_field_service.fs_request_form', self._fs_request_values())

    def _fs_check(self, post):
        errors = {}
        public = request.env.user._is_public()
        if not (post.get('name') or '').strip():
            errors['name'] = request.env._("Tell us what the visit is for.")
        if public:
            if not (post.get('contact_name') or '').strip():
                errors['contact_name'] = request.env._("Your name is needed.")
            if not email_normalize(post.get('email') or ''):
                errors['email'] = request.env._("A valid email is needed to send you the confirmation.")
        if not post.get('site_id') and not (post.get('street') and post.get('city')):
            errors['street'] = request.env._("Give the address of the site: street and city.")
        for key in ('preferred_date', 'preferred_date_to'):
            if post.get(key):
                try:
                    fields.Date.to_date(post[key])
                except ValueError:
                    errors[key] = request.env._("This date is not valid.")
        return errors

    @http.route(['/field-service/request/submit'], type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def fs_request_submit(self, **post):
        errors = self._fs_check(post)
        if errors:
            return request.render('om_website_field_service.fs_request_form',
                                  self._fs_request_values(errors=errors, values=post))
        Task = request.env['project.task'].sudo()
        user = request.env.user
        if user._is_public():
            partner = Task._fs_find_or_create_partner(post.get('contact_name'), post.get('email'), post.get('phone'))
        else:
            partner = user.partner_id.sudo()
        site = request.env['res.partner']
        site_id = int(post['site_id']) if (post.get('site_id') or '').isdigit() else False
        if site_id and not user._is_public():
            site = request.env['res.partner'].sudo().search(
                [('id', '=', site_id), ('id', 'child_of', partner.commercial_partner_id.id)], limit=1)
        if not site:
            country_id = int(post['country_id']) if (post.get('country_id') or '').isdigit() else False
            site = Task._fs_find_or_create_site(partner, {
                'street': post.get('street'),
                'street2': post.get('street2'),
                'zip': post.get('zip'),
                'city': post.get('city'),
                'country_id': country_id,
            })
        photos = []
        for upload in request.httprequest.files.getlist('photos')[:MAX_PHOTOS]:
            content = upload.read(MAX_PHOTO_SIZE + 1)
            if content and len(content) <= MAX_PHOTO_SIZE:
                photos.append((upload.filename or 'photo', content))
        preferred_time = post.get('preferred_time')
        job = Task._fs_create_online_request(partner, site, {
            'name': post.get('name', '').strip(),
            'description': post.get('description'),
            'equipment': post.get('equipment'),
            'serial': post.get('serial'),
            'phone': post.get('phone'),
            'preferred_date': post.get('preferred_date') or False,
            'preferred_date_to': post.get('preferred_date_to') or False,
            'preferred_time': preferred_time if preferred_time in dict(PREFERRED_TIMES) else False,
        }, photos=photos)
        request.session['om_fs_request_id'] = job.id
        return request.redirect('/field-service/request/thanks')

    @http.route(['/field-service/request/thanks'], type='http', auth='public', website=True, sitemap=False)
    def fs_request_thanks(self, **kw):
        job = request.env['project.task']
        if request.session.get('om_fs_request_id'):
            job = job.sudo().browse(request.session['om_fs_request_id']).exists()
        return request.render('om_website_field_service.fs_request_thanks', {
            'job': job,
            'is_public': request.env.user._is_public(),
        })
