from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class CommissionPortal(CustomerPortal):

    def _commission_portal_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        return [('partner_id', 'child_of', partner.id), ('user_id', '=', False),
                ('state', 'in', ('approved', 'paid'))]

    def _prepare_portal_counter_values(self, counter):
        if counter == 'commission_count':
            return 'om.commission.statement', self._commission_portal_domain(), 'read'
        return super()._prepare_portal_counter_values(counter)

    @http.route(['/my/commissions', '/my/commissions/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_commissions(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        Statement = request.env['om.commission.statement']
        domain = self._commission_portal_domain()
        has_access = Statement.has_access('read')
        count = Statement.search_count(domain) if has_access else 0
        pager = portal_pager(url='/my/commissions', total=count, page=page, step=self._items_per_page)
        statements = Statement.search(domain, limit=self._items_per_page, offset=pager['offset']) \
            if has_access else Statement
        request.session['my_commissions_history'] = statements.ids[:100]
        values.update({
            'statements': statements,
            'page_name': 'commission',
            'pager': pager,
            'default_url': '/my/commissions',
        })
        return request.render('om_sale_commission.portal_my_commissions', values)

    @http.route(['/my/commissions/<int:statement_id>'], type='http', auth='public', website=True)
    def portal_commission_page(self, statement_id, access_token=None, report_type=None, download=False, **kw):
        try:
            statement_sudo = self._document_check_access('om.commission.statement', statement_id,
                                                         access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if statement_sudo.state not in ('approved', 'paid'):
            return request.redirect('/my')
        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=statement_sudo, report_type=report_type,
                                     report_ref='om_sale_commission.action_report_commission_statement',
                                     download=download)
        values = {
            'statement': statement_sudo,
            'page_name': 'commission',
            'res_company': statement_sudo.company_id,
        }
        values = self._get_page_view_values(statement_sudo, access_token, values, 'my_commissions_history', False,
                                            **kw)
        return request.render('om_sale_commission.portal_commission_page', values)
