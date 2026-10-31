import logging

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import CustomerPortal

_logger = logging.getLogger(__name__)


class SignPortal(CustomerPortal):
    """ The signing pages. A signer reaches their own signature only, by the secret link emailed to them, logged in
    or not; nothing else is reached by changing an id in the address. """

    def _prepare_portal_counter_values(self, counter):
        if counter == 'sign_count':
            return 'sign.request.signer', self._my_signers_domain(to_sign=True), 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @staticmethod
    def _my_signers_domain(to_sign=False):
        domain = [('partner_id', '=', request.env.user.partner_id.id), ('request_id.state', '!=', 'draft')]
        if to_sign:
            domain += [('state', '=', 'to_sign'), ('request_id.state', '=', 'sent')]
        return domain

    @staticmethod
    def _signer(signer_id, token):
        """ :return: the signer of that id when the token is theirs, as the super user; 404 otherwise """
        signer = request.env['sign.request.signer'].sudo().browse(signer_id).exists()
        if not signer or not signer._check_token(token) or signer.request_id.state == 'draft':
            raise NotFound()
        return signer

    @staticmethod
    def _pdf_response(sign_request, download=False):
        """ :return: the PDF to sign, or the signed one once everyone signed """
        if sign_request.state == 'signed' and sign_request.signed_attachment_id:
            data, name = sign_request.signed_attachment_id.raw.content, sign_request.signed_attachment_id.name
        else:
            data, name = sign_request._get_document(), sign_request.document_filename or 'document.pdf'
        disposition = 'attachment' if download else 'inline'
        return request.make_response(data, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(name, disposition_type=disposition)),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @staticmethod
    def _readonly_values(sign_request, status, document_url):
        """ :return: what the read-only signing page shows: the document, the fields filled so far """
        return {
            'fields': [],
            'others': [],
            'shown': sign_request._shown_values(),
            'can_sign': False,
            'needs_code': False,
            'status': status,
            'signed_count': sign_request.signed_count,
            'signer_count': sign_request.signer_count,
            'page_count': sign_request.sign_template_id.page_count or 0,
            'document_url': document_url,
        }

    def _page(self, signer, **values):
        return request.render('om_sign.sign_page', {
            'signer': signer,
            'sign_request': signer.request_id,
            'base_url': '/sign/%s/%s' % (signer.id, signer.access_token),
            **values,
        })

    @http.route('/sign/<int:signer_id>/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def sign_page(self, signer_id, token, **kwargs):
        signer = self._signer(signer_id, token)
        signer._opened()
        return self._page(signer)

    @http.route('/sign/<int:signer_id>/<string:token>/document', type='http', auth='public', sitemap=False)
    def sign_document(self, signer_id, token, **kwargs):
        """ The PDF to sign, or the signed one once everyone signed. """
        signer = self._signer(signer_id, token)
        return self._pdf_response(signer.request_id, download=kwargs.get('download'))

    @http.route('/sign/<int:signer_id>/<string:token>/code', type='http', auth='public', methods=['POST'],
                website=True, sitemap=False)
    def sign_code(self, signer_id, token, code=None, **kwargs):
        """ Send the email code, or check the one entered. """
        signer = self._signer(signer_id, token)
        try:
            if code is None:
                sent = signer._send_code()
                return self._page(signer, message='code_sent' if sent else 'code_wait')
            if not signer._verify_code(code):
                return self._page(signer, error='code_wrong')
        except UserError as error:
            return self._page(signer, error=str(error))
        return request.redirect('/sign/%s/%s' % (signer.id, token))

    @http.route('/sign/<int:signer_id>/<string:token>/accept', type='jsonrpc', auth='public', website=True)
    def sign_accept(self, signer_id, token, name=None, signature=None):
        signer = self._signer(signer_id, token)
        try:
            with request.env.cr.savepoint():
                signer._sign(name, signature)
        except UserError as error:
            return {'error': str(error)}
        return {'force_refresh': True, 'redirect_url': '/sign/%s/%s' % (signer.id, token)}

    @http.route('/sign/<int:signer_id>/<string:token>/fields', type='jsonrpc', auth='public', website=True)
    def sign_fields(self, signer_id, token):
        """ The fields the signer fills, and whether they can sign now. """
        signer = self._signer(signer_id, token)
        sign_request = signer.request_id
        document_url = '/sign/%s/%s/document' % (signer.id, token)
        status = signer._readonly_status()
        if status:
            return {**self._readonly_values(sign_request, status, document_url), 'state': signer.state,
                    'name': signer.partner_id.name}
        return {
            'fields': signer._signing_fields(),
            'others': signer._others_fields(),
            'can_sign': sign_request.state == 'sent' and signer.state == 'to_sign',
            'needs_code': signer._needs_code(),
            'state': signer.state,
            'name': signer.partner_id.name,
            'page_count': sign_request.sign_template_id.page_count or 0,
            'document_url': document_url,
        }

    @http.route('/sign/<int:signer_id>/<string:token>/fields/submit', type='jsonrpc', auth='public', website=True)
    def sign_fields_submit(self, signer_id, token, values=None, name=None):
        """ Sign, filling the fields: see sign.request.signer._sign_fields(). """
        signer = self._signer(signer_id, token)
        try:
            with request.env.cr.savepoint():
                signer._sign_fields(values or {}, name=name)
        except UserError as error:
            return {'error': str(error)}
        return {'force_refresh': True, 'redirect_url': '/sign/%s/%s' % (signer.id, token)}

    @http.route('/sign/<int:signer_id>/<string:token>/decline', type='http', auth='public', methods=['POST'],
                website=True, sitemap=False)
    def sign_decline(self, signer_id, token, reason=None, **kwargs):
        signer = self._signer(signer_id, token)
        try:
            signer._decline(reason)
        except UserError as error:
            return self._page(signer, error=str(error))
        return request.redirect('/sign/%s/%s' % (signer.id, token))

    @http.route('/sign/verify/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def sign_verify(self, token, **kwargs):
        """ The public page the certificate of a signed PDF names: who signed it and its fingerprint. """
        sign_request = request.env['sign.request'].sudo().search(
            [('access_token', '=', token), ('state', '!=', 'draft')], limit=1) if token else None
        return request.render('om_sign.verify_page', {'sign_request': sign_request})

    # ------------------------------------------------------------------
    # The copy recipients: the document, read-only
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_request(request_id, partner_id, token):
        """ :return: the request and the copy recipient of the link, as the super user; 404 otherwise """
        sign_request = request.env['sign.request'].sudo().browse(request_id).exists()
        partner = request.env['res.partner'].sudo().browse(partner_id).exists()
        if not sign_request or not partner or sign_request.state == 'draft' or \
                not sign_request._check_copy_token(partner, token):
            raise NotFound()
        return sign_request, partner

    @staticmethod
    def _copy_status(sign_request):
        if sign_request.state == 'signed':
            return 'copy_completed'
        return 'copy_waiting' if sign_request.state == 'sent' else 'copy_closed'

    @http.route('/sign/copy/<int:request_id>/<int:partner_id>/<string:token>', type='http', auth='public',
                website=True, sitemap=False)
    def sign_copy_page(self, request_id, partner_id, token, **kwargs):
        sign_request, partner = self._copy_request(request_id, partner_id, token)
        return request.render('om_sign.copy_page', {
            'sign_request': sign_request,
            'partner': partner,
            'base_url': '/sign/copy/%s/%s/%s' % (sign_request.id, partner.id, token),
        })

    @http.route('/sign/copy/<int:request_id>/<int:partner_id>/<string:token>/document', type='http',
                auth='public', sitemap=False)
    def sign_copy_document(self, request_id, partner_id, token, **kwargs):
        sign_request, _partner = self._copy_request(request_id, partner_id, token)
        return self._pdf_response(sign_request, download=kwargs.get('download'))

    @http.route('/sign/copy/<int:request_id>/<int:partner_id>/<string:token>/fields', type='jsonrpc',
                auth='public', website=True)
    def sign_copy_fields(self, request_id, partner_id, token):
        sign_request, partner = self._copy_request(request_id, partner_id, token)
        return {**self._readonly_values(sign_request, self._copy_status(sign_request),
                                        '/sign/copy/%s/%s/%s/document' % (sign_request.id, partner.id, token)),
                'name': partner.name}

    # ------------------------------------------------------------------
    # The shared link of a template
    # ------------------------------------------------------------------

    @staticmethod
    def _shared_template(template_id, token):
        """ :return: the template shared by that link, as the super user; 404 when it is not or no longer """
        template = request.env['sign.template'].sudo().browse(template_id).exists()
        if not template or not template.active or not template.share_enabled or template.share_problem or \
                not token or not consteq(template.share_token or '', token):
            raise NotFound()
        return template

    def _share_page(self, template, token, step='start', **values):
        return request.render('om_sign.share_page', {
            'template': template,
            'company': template.company_id or template._share_user().company_id,
            'base_url': '/sign/share/%s/%s' % (template.id, token),
            'step': step,
            **values,
        })

    @http.route('/sign/share/<int:template_id>/<string:token>', type='http', auth='public', website=True,
                sitemap=False)
    def sign_share_page(self, template_id, token, **kwargs):
        return self._share_page(self._shared_template(template_id, token), token)

    @http.route('/sign/share/<int:template_id>/<string:token>/code', type='http', auth='public',
                methods=['POST'], website=True, sitemap=False)
    def sign_share_code(self, template_id, token, name=None, email=None, visit=None, website=None, **kwargs):
        """ The visitor gives their name and email, or asks for a new code: a code is emailed to them. """
        template = self._shared_template(template_id, token)
        Visit = request.env['sign.share.visit'].sudo()
        if website:
            # the field hidden to people: filled by a robot, nothing is sent
            _logger.info('Shared link of sign template %s: robot ignored', template.id)
            return self._share_page(template, token, step='code', email=email, visit_token='')
        if visit:
            found = Visit.search([('template_id', '=', template.id), ('access_token', '=', visit)], limit=1)
            if not found or not found._check_token(visit):
                return self._share_page(template, token, error='start_again')
            sent = found._send_code()
            return self._share_page(template, token, step='code', email=found.email, visit_token=visit,
                                    message='code_sent' if sent else 'code_wait')
        try:
            with request.env.cr.savepoint():
                found = Visit._start(template, name, email, request.httprequest.remote_addr)
        except UserError as error:
            return self._share_page(template, token, error=str(error), name=name, email=email)
        return self._share_page(template, token, step='code', email=found.email,
                                visit_token=found.access_token, message='code_sent')

    @http.route('/sign/share/<int:template_id>/<string:token>/verify', type='http', auth='public',
                methods=['POST'], website=True, sitemap=False)
    def sign_share_verify(self, template_id, token, visit=None, code=None, **kwargs):
        """ The visitor enters the code: the request is made and sent, and they sign it. """
        template = self._shared_template(template_id, token)
        found = request.env['sign.share.visit'].sudo().search(
            [('template_id', '=', template.id), ('access_token', '=', visit or '')], limit=1) if visit else None
        if not found or not found._check_token(visit) or found.request_id:
            return self._share_page(template, token, error='start_again')
        if not found._verify_code(code):
            return self._share_page(template, token, step='code', email=found.email, visit_token=visit,
                                    error='code_wrong')
        try:
            with request.env.cr.savepoint():
                signer = found._create_request()
        except UserError as error:
            return self._share_page(template, token, error=str(error))
        return request.redirect('/sign/%s/%s' % (signer.id, signer.sudo().access_token))

    @http.route('/my/signatures', type='http', auth='user', website=True)
    def my_signatures(self, **kwargs):
        signers = request.env['sign.request.signer'].sudo().search(self._my_signers_domain(), order='id desc')
        return request.render('om_sign.portal_my_signatures', {
            **self._prepare_portal_layout_values(), 'signers': signers, 'page_name': 'signatures'})
