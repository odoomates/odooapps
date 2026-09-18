from werkzeug.exceptions import NotFound

from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition

XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class StatementController(Controller):

    @route('/om_account_followup/statement/<string:statement_type>/xlsx', type='http', auth='user')
    def statement_xlsx(self, statement_type, partner_ids='', **kwargs):
        if statement_type not in ('customer', 'vendor') \
                or not request.env.user.has_group('account.group_account_invoice'):
            raise NotFound()
        ids = [int(partner_id) for partner_id in partner_ids.split(',') if partner_id.isdigit()]
        # the partners the user cannot read raise an access error
        partners = request.env['res.partner'].browse(ids).exists()
        partners.check_access('read')
        if not partners:
            raise NotFound()
        content = partners._statement_xlsx(statement_type)
        return request.make_response(content, [
            ('Content-Type', XLSX_CONTENT_TYPE),
            ('Content-Disposition', content_disposition(partners._statement_xlsx_filename(statement_type))),
        ])
