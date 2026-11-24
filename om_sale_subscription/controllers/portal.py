from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.sale.controllers.portal import CustomerPortal


class SubscriptionPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'subscription_count':
            partner = self.env.user.partner_id
            return 'sale.order', self.env['sale.order']._subscription_portal_domain(partner), 'read'
        return super()._prepare_portal_counter_values(counter)

    def _subscription_check_access(self, order_id, access_token):
        order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        if not order_sudo.is_subscription or order_sudo.state != 'sale':
            raise MissingError(self.env._('This subscription does not exist.'))
        return order_sudo

    def _subscription_is_owner(self, order_sudo):
        """Only the logged in customer can change the payment method or the status of the subscription."""
        user = self.env.user
        return not user._is_public() and (
            user.partner_id.commercial_partner_id == order_sudo.partner_id.commercial_partner_id)

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth='user',
                website=True)
    def portal_my_subscriptions(self, page=1, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        SaleOrder = self.env['sale.order']
        domain = SaleOrder._subscription_portal_domain(self.env.user.partner_id)
        filters = {
            'all': {'label': self.env._('All'), 'domain': []},
            'running': {'label': self.env._('Running'),
                        'domain': [('subscription_state', 'in', ('progress', 'paused'))]},
            'closed': {'label': self.env._('Closed'),
                       'domain': [('subscription_state', 'in', ('churn', 'renewed'))]},
        }
        filterby = filterby if filterby in filters else 'running'
        domain &= Domain(filters[filterby]['domain'])
        has_access = SaleOrder.has_access('read')
        count = SaleOrder.search_count(domain) if has_access else 0
        pager = portal_pager(url='/my/subscriptions', total=count, page=page, step=self._items_per_page,
                             url_args={'filterby': filterby})
        orders = SaleOrder.search(domain, order='subscription_state, id desc', limit=self._items_per_page,
                                  offset=pager['offset']) if has_access else SaleOrder
        request.session['my_subscriptions_history'] = orders.ids[:100]
        values.update({
            'subscriptions': orders.sudo(),
            'page_name': 'subscription',
            'pager': pager,
            'default_url': '/my/subscriptions',
            'searchbar_filters': filters,
            'filterby': filterby,
        })
        return request.render('om_sale_subscription.portal_my_subscriptions', values)

    @http.route(['/my/subscriptions/<int:order_id>'], type='http', auth='public', website=True)
    def portal_subscription_page(self, order_id, access_token=None, message=None, **kw):
        try:
            order_sudo = self._subscription_check_access(order_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        is_owner = self._subscription_is_owner(order_sudo)
        invoices = (order_sudo.subscription_invoice_ids | order_sudo.invoice_ids).filtered(
            lambda inv: inv.state == 'posted').sorted('invoice_date', reverse=True)
        tokens = request.env['payment.token']
        if is_owner:
            tokens = tokens.sudo().search([
                ('partner_id', 'child_of', order_sudo.partner_id.commercial_partner_id.id),
                ('active', '=', True),
                ('provider_id.company_id', '=', order_sudo.company_id.id),
            ])
        plan = order_sudo.subscription_plan_id
        values = {
            'subscription': order_sudo.with_context(lang=order_sudo._get_lang()),
            'page_name': 'subscription',
            'invoices': invoices,
            'open_invoices': invoices.filtered(lambda inv: inv.payment_state in ('not_paid', 'partial')
                                               and inv.move_type == 'out_invoice'),
            'tokens': tokens,
            'is_owner': is_owner,
            'can_close': is_owner and plan.user_closable and order_sudo.subscription_state in ('progress', 'paused'),
            'can_pause': is_owner and plan.user_pausable and order_sudo.subscription_state == 'progress',
            'can_resume': is_owner and plan.user_pausable and order_sudo.subscription_state == 'paused',
            'close_reasons': request.env['om.subscription.close.reason'].sudo().search(
                [('visible_in_portal', '=', True)]),
            'message': message,
            'res_company': order_sudo.company_id,
            'access_token': access_token,
        }
        values = self._get_page_view_values(order_sudo, access_token, values, 'my_subscriptions_history', False,
                                            **kw)
        return request.render('om_sale_subscription.portal_subscription_page', values)

    def _subscription_redirect(self, order_sudo, access_token, message=None):
        url = f'/my/subscriptions/{order_sudo.id}'
        params = []
        if access_token:
            params.append(f'access_token={access_token}')
        if message:
            params.append(f'message={message}')
        return request.redirect(url + ('?' + '&'.join(params) if params else ''))

    def _subscription_owner_or_redirect(self, order_id, access_token):
        try:
            order_sudo = self._subscription_check_access(order_id, access_token)
        except (AccessError, MissingError):
            return None
        if not self._subscription_is_owner(order_sudo):
            return None
        return order_sudo

    @http.route(['/my/subscriptions/<int:order_id>/close'], type='http', auth='user', methods=['POST'],
                website=True)
    def portal_subscription_close(self, order_id, access_token=None, close_reason_id=None, note=None, **kw):
        order_sudo = self._subscription_owner_or_redirect(order_id, access_token)
        if not order_sudo:
            return request.redirect('/my')
        if order_sudo.subscription_plan_id.user_closable and order_sudo.subscription_state in ('progress', 'paused'):
            reason = request.env['om.subscription.close.reason'].sudo().search([
                ('id', '=', self._cast_as_int(close_reason_id) or 0), ('visible_in_portal', '=', True)], limit=1)
            order_sudo._subscription_close(reason=reason, note=note)
            return self._subscription_redirect(order_sudo, access_token, 'closed')
        return self._subscription_redirect(order_sudo, access_token)

    @http.route(['/my/subscriptions/<int:order_id>/pause'], type='http', auth='user', methods=['POST'],
                website=True)
    def portal_subscription_pause(self, order_id, access_token=None, **kw):
        order_sudo = self._subscription_owner_or_redirect(order_id, access_token)
        if not order_sudo:
            return request.redirect('/my')
        if order_sudo.subscription_plan_id.user_pausable and order_sudo.subscription_state == 'progress':
            order_sudo.action_subscription_pause()
            order_sudo.message_post(body=self.env._('Paused by the customer from the portal.'))
        return self._subscription_redirect(order_sudo, access_token)

    @http.route(['/my/subscriptions/<int:order_id>/resume'], type='http', auth='user', methods=['POST'],
                website=True)
    def portal_subscription_resume(self, order_id, access_token=None, **kw):
        order_sudo = self._subscription_owner_or_redirect(order_id, access_token)
        if not order_sudo:
            return request.redirect('/my')
        if order_sudo.subscription_plan_id.user_pausable and order_sudo.subscription_state == 'paused':
            order_sudo.action_subscription_resume()
            order_sudo.message_post(body=self.env._('Resumed by the customer from the portal.'))
        return self._subscription_redirect(order_sudo, access_token)

    @http.route(['/my/subscriptions/<int:order_id>/payment_method'], type='http', auth='user', methods=['POST'],
                website=True)
    def portal_subscription_payment_method(self, order_id, access_token=None, token_id=None, **kw):
        order_sudo = self._subscription_owner_or_redirect(order_id, access_token)
        if not order_sudo:
            return request.redirect('/my')
        token = request.env['payment.token'].sudo().search([
            ('id', '=', self._cast_as_int(token_id) or 0),
            ('partner_id', 'child_of', order_sudo.partner_id.commercial_partner_id.id),
            ('active', '=', True),
        ], limit=1)
        order_sudo.subscription_token_id = token
        return self._subscription_redirect(order_sudo, access_token, 'payment_method')
