import io
import zipfile

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import CustomerPortal


def make_zip(documents):
    """ :return: the bytes of a zip of the files of `documents`, each name used once """
    stream = io.BytesIO()
    names = set()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for document in documents.filtered('attachment_id'):
            name = document.file_name or document.attachment_id.name or document.name
            base, dot, extension = name.rpartition('.')
            if not dot:
                base, extension = name, ''
            candidate, index = name, 1
            while candidate in names:
                candidate = '%s (%s)%s' % (base, index, '.' + extension if extension else '')
                index += 1
            names.add(candidate)
            archive.writestr(candidate, document._get_raw())
    return stream.getvalue()


def zip_response(content, name):
    return request.make_response(content, headers=[
        ('Content-Type', 'application/zip'),
        ('X-Content-Type-Options', 'nosniff'),
        ('Content-Length', len(content)),
        ('Content-Disposition', content_disposition(name)),
    ])


class DocumentsController(http.Controller):

    @http.route('/om_documents/zip', type='http', auth='user')
    def documents_zip(self, ids='', **kwargs):
        try:
            document_ids = [int(i) for i in ids.split(',') if i]
        except ValueError:
            raise NotFound() from None
        documents = request.env['om.documents.document'].browse(document_ids).exists()
        documents.check_access('read')
        return zip_response(make_zip(documents), 'documents.zip')


class DocumentsShareController(CustomerPortal):
    """ The pages of the shared links. A visitor reaches what the link shares only, by its secret token. """

    @staticmethod
    def _get_share(share_id, token):
        share = request.env['om.documents.share'].sudo().with_context(active_test=False).browse(share_id).exists()
        if not share or not token or not consteq(share.access_token, token):
            raise NotFound()
        return share

    def _share_values(self, share, **values):
        base = '/documents/share/%s/%s' % (share.id, share.access_token)
        return {'share': share, 'base_url': base, 'documents': share._get_documents(), **values}

    @http.route('/documents/share/<int:share_id>/<string:token>', type='http', auth='public', website=True,
                sitemap=False)
    def share_page(self, share_id, token, uploaded=None, **kwargs):
        share = self._get_share(share_id, token)
        if not share._check_live():
            share._log('expired', request=request)
            return request.render('om_documents.share_expired', {'share': share}, status=410)
        share._log('view', request=request)
        return request.render('om_documents.share_page', self._share_values(share, uploaded=uploaded))

    def _shared_document(self, share, document_id):
        if not share._check_live():
            share._log('expired', request=request)
            raise Forbidden()
        document = share._get_documents().filtered(lambda d: d.id == document_id)
        if not document:
            raise NotFound()
        return document

    @http.route('/documents/share/<int:share_id>/<string:token>/file/<int:document_id>', type='http',
                auth='public', sitemap=False)
    def share_file(self, share_id, token, document_id, download=None, **kwargs):
        share = self._get_share(share_id, token)
        document = self._shared_document(share, document_id)
        if document.type == 'url':
            return request.redirect(document.url, local=False)
        if download and not share.allow_download:
            raise Forbidden()
        if download:
            share._log('download', document=document, request=request)
        stream = request.env['ir.binary']._get_stream_from(document.attachment_id.sudo(), 'raw')
        return stream.get_response(as_attachment=bool(download))

    @http.route('/documents/share/<int:share_id>/<string:token>/zip', type='http', auth='public', sitemap=False)
    def share_zip(self, share_id, token, **kwargs):
        share = self._get_share(share_id, token)
        if not share._check_live():
            share._log('expired', request=request)
            raise Forbidden()
        if not share.allow_download:
            raise Forbidden()
        share._log('download_all', request=request)
        return zip_response(make_zip(share._get_documents()), '%s.zip' % share.name)

    @http.route('/documents/share/<int:share_id>/<string:token>/upload', type='http', auth='public',
                methods=['POST'], website=True, sitemap=False)
    def share_upload(self, share_id, token, **kwargs):
        share = self._get_share(share_id, token)
        if not share._check_live():
            return request.render('om_documents.share_expired', {'share': share}, status=410)
        if not share.allow_upload:
            raise Forbidden()
        files = [(file.filename, file.mimetype, file.read())
                 for file in request.httprequest.files.getlist('files') if file.filename]
        partner = request.env.user.partner_id if not request.env.user._is_public() else None
        documents = share._upload(files, partner=partner) if files else share.env['om.documents.document']
        for document in documents:
            share._log('upload', document=document, request=request)
        return request.redirect('/documents/share/%s/%s?uploaded=%s' % (share.id, token, len(documents)))

    # ------------------------------------------------------------------
    # Portal: the documents shared with the contact of the user
    # ------------------------------------------------------------------

    @staticmethod
    def _my_shares_domain():
        return [('partner_ids', 'in', request.env.user.partner_id.ids), ('state', 'in', ['live'])]

    def _prepare_portal_counter_values(self, counter):
        if counter == 'om_documents_count':
            return 'om.documents.share', self._my_shares_domain(), 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @http.route('/my/documents', type='http', auth='user', website=True)
    def my_documents(self, **kwargs):
        shares = request.env['om.documents.share'].sudo().search(self._my_shares_domain())
        return request.render('om_documents.portal_my_documents', {
            **self._prepare_portal_layout_values(), 'shares': shares, 'page_name': 'om_documents'})
