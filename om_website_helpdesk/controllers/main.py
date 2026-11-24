from odoo import http
from odoo.http import request

from odoo.addons.website.controllers import form


class WebsiteHelpdesk(http.Controller):

    @http.route(['/helpdesk'], type='http', auth='public', website=True, sitemap=True)
    def helpdesk_teams(self, **kw):
        teams = request.env['om.helpdesk.team']._get_website_teams(request.env.website)
        return request.render('om_website_helpdesk.helpdesk_teams', {'teams': teams})

    @http.route(['/helpdesk/<model("om.helpdesk.team"):team>'], type='http', auth='public', website=True, sitemap=True)
    def helpdesk_team_form(self, team, **kw):
        team_sudo = team.sudo()
        if team_sudo not in request.env['om.helpdesk.team']._get_website_teams(request.env.website):
            return request.not_found()
        user = request.env.user
        values = {
            'team': team_sudo,
            'teams': request.env['om.helpdesk.team']._get_website_teams(request.env.website),
            'default_values': {} if user._is_public() else {
                'partner_name': user.partner_id.name,
                'email_from': user.partner_id.email,
                'partner_phone': user.partner_id.phone,
            },
        }
        return request.render('om_website_helpdesk.helpdesk_team_form', values)

    @http.route(['/helpdesk/thanks'], type='http', auth='public', website=True, sitemap=False)
    def helpdesk_thanks(self, **kw):
        ticket = request.env['om.helpdesk.ticket']
        if request.session.get('form_builder_model_model') == 'om.helpdesk.ticket' and request.session.get('form_builder_id'):
            ticket = ticket.sudo().browse(request.session['form_builder_id']).exists()
        portal_url = False
        if ticket and ticket.team_id.privacy_visibility == 'portal':
            portal_url = ticket.get_portal_url()
        return request.render('om_website_helpdesk.helpdesk_thanks', {'ticket': ticket, 'portal_url': portal_url})


class WebsiteForm(form.WebsiteForm):

    def extract_data(self, model_sudo, values):
        data = super().extract_data(model_sudo, values)
        if model_sudo.model == 'om.helpdesk.ticket':
            record = data['record']
            teams = request.env['om.helpdesk.team']._get_website_teams(request.env.website)
            team_id = record.get('team_id')
            if team_id not in teams.ids:
                record['team_id'] = teams[:1].id or False
            user = request.env.user
            if user.share and not user._is_public():
                # a signed-in customer: the ticket is theirs, whatever email they typed
                record['partner_id'] = user.partner_id.id
                record.setdefault('email_from', user.partner_id.email)
        return data

    def insert_record(self, request, model_sudo, values, custom, meta=None):
        if model_sudo.model == 'om.helpdesk.ticket' and not values.get('partner_id') and values.get('email_from'):
            values['partner_id'] = request.env['om.helpdesk.ticket'].sudo()._find_or_create_partner(
                values['email_from'], values.get('partner_name'), values.get('partner_phone')).id
        return super().insert_record(request, model_sudo, values, custom, meta=meta)
