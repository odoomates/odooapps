from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class HelpdeskCustomerPortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'om_ticket_count':
            return 'om.helpdesk.ticket', [], 'read'
        return super()._prepare_portal_counter_values(counter)

    def _ticket_searchbar_sortings(self):
        return {
            'date': {'label': self.env._('Newest'), 'order': 'create_date desc, id desc'},
            'update': {'label': self.env._('Last Update'), 'order': 'write_date desc, id desc'},
            'name': {'label': self.env._('Subject'), 'order': 'name, id'},
            'stage': {'label': self.env._('Stage'), 'order': 'stage_id, id desc'},
            'priority': {'label': self.env._('Priority'), 'order': 'priority desc, id desc'},
        }

    def _ticket_searchbar_filters(self):
        return {
            'all': {'label': self.env._('All'), 'domain': []},
            'open': {'label': self.env._('Open'), 'domain': [('is_closed', '=', False)]},
            'closed': {'label': self.env._('Closed'), 'domain': [('is_closed', '=', True)]},
        }

    def _ticket_searchbar_inputs(self):
        return {
            'content': {'input': 'content', 'label': self.env._('Search in Subject and Number')},
            'message': {'input': 'message', 'label': self.env._('Search in Messages')},
            'all': {'input': 'all', 'label': self.env._('Search in All')},
        }

    def _ticket_search_domain(self, search_in, search):
        if not search:
            return Domain.TRUE
        content = Domain('name', 'ilike', search) | Domain('number', 'ilike', search)
        message = Domain('message_ids.body', 'ilike', search)
        if search_in == 'message':
            return message
        if search_in == 'all':
            return content | message
        return content

    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_tickets(self, page=1, sortby=None, filterby=None, search=None, search_in='content', **kw):
        values = self._prepare_portal_layout_values()
        Ticket = request.env['om.helpdesk.ticket']
        sortings = self._ticket_searchbar_sortings()
        filters = self._ticket_searchbar_filters()
        sortby = sortby if sortby in sortings else 'date'
        filterby = filterby if filterby in filters else 'open'
        domain = Domain(filters[filterby]['domain']) & self._ticket_search_domain(search_in, search)

        ticket_count = Ticket.search_count(domain)
        pager = portal_pager(
            url='/my/tickets',
            url_args={'sortby': sortby, 'filterby': filterby, 'search': search, 'search_in': search_in},
            total=ticket_count,
            page=page,
            step=self._items_per_page,
        )
        tickets = Ticket.search(domain, order=sortings[sortby]['order'], limit=self._items_per_page, offset=pager['offset'])
        request.session['my_tickets_history'] = tickets.ids[:100]
        values.update({
            'tickets': tickets,
            'page_name': 'ticket',
            'default_url': '/my/tickets',
            'pager': pager,
            'searchbar_sortings': sortings,
            'searchbar_filters': filters,
            'searchbar_inputs': self._ticket_searchbar_inputs(),
            'search_in': search_in,
            'search': search,
            'sortby': sortby,
            'filterby': filterby,
        })
        return request.render('om_helpdesk.portal_my_tickets', values)

    def _ticket_get_page_view_values(self, ticket, access_token, **kwargs):
        values = {
            'page_name': 'ticket',
            'ticket': ticket,
            'user': request.env.user,
            'priority_labels': dict(ticket._fields['priority']._description_selection(request.env)),
            'can_close': not ticket.is_closed and bool(ticket._get_closing_stage()),
            'rating_token': False,
            'rating_done': False,
        }
        if ticket.is_closed and ticket.team_id.use_rating and ticket.partner_id:
            rated = ticket.rating_ids.filtered(lambda r: r.consumed and r.partner_id == ticket.partner_id)
            if rated:
                values['rating_done'] = rated.sorted('write_date', reverse=True)[:1]
            else:
                values['rating_token'] = ticket.rating_get_portal_token()
        return self._get_page_view_values(ticket, access_token, values, 'my_tickets_history', False, **kwargs)

    @http.route(['/my/tickets/<int:ticket_id>'], type='http', auth='public', website=True)
    def portal_my_ticket(self, ticket_id, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access('om.helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        ticket_sudo._portal_ensure_token()
        for attachment in ticket_sudo.message_ids.attachment_ids:
            attachment.generate_access_token()
        values = self._ticket_get_page_view_values(ticket_sudo, access_token, **kw)
        return request.render('om_helpdesk.portal_my_ticket', values)

    @http.route(['/my/tickets/<int:ticket_id>/close'], type='http', auth='public', website=True, methods=['POST'])
    def portal_close_ticket(self, ticket_id, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access('om.helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if not ticket_sudo.is_closed:
            stage = ticket_sudo._get_closing_stage()
            if stage:
                author = request.env.user.partner_id if not request.env.user._is_public() else ticket_sudo.partner_id
                ticket_sudo.stage_id = stage
                ticket_sudo.message_post(
                    body=Markup('<p>%s</p>') % self.env._('The customer closed the ticket.'),
                    author_id=author.id,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
        url = ticket_sudo.get_portal_url() if access_token else f'/my/tickets/{ticket_sudo.id}'
        return request.redirect(url)
