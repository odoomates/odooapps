# Sign-ins, failed sign-ins and the sign-in emails.
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessDenied
from odoo.http import request

from .client_call import client_address

SIGN_IN_EVENTS = ('login', 'login_failed', 'logout', 'session_end')


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_audit_log_count = fields.Integer(compute='_compute_om_audit_counts', groups='base.group_system')
    om_session_count = fields.Integer(compute='_compute_om_audit_counts', groups='base.group_system')

    def _compute_om_audit_counts(self):
        Log = self.env['om.user.audit.log'].sudo()
        logs = {
            group['user_id'][0]: group['user_id_count']
            for group in Log._read_group([('user_id', 'in', self.ids)], ['user_id'], ['user_id'])
        }
        sessions = {
            group['user_id'][0]: group['user_id_count']
            for group in self.env['om.user.audit.session'].sudo()._read_group(
                [('user_id', 'in', self.ids), ('revoked', '=', False)], ['user_id'], ['user_id'])
        }
        for user in self:
            user.om_audit_log_count = logs.get(user.id, 0)
            user.om_session_count = sessions.get(user.id, 0)

    @classmethod
    def _login(cls, db, login, password, user_agent_env):
        # Odoo 16 signs in on a cursor of its own: so is the log written
        values = {'ip': client_address() or False}
        if request:
            values['user_agent'] = (request.httprequest.user_agent.string or '')[:500] or False
        interactive = (user_agent_env or {}).get('interactive', True)
        try:
            uid = super()._login(db, login, password, user_agent_env)
        except AccessDenied as error:
            login = login or ''
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                user = env['res.users'].with_context(active_test=False).search([('login', '=', login)], limit=1)
                env['om.user.audit.log']._om_log(
                    'login_failed', separate=True, user_id=user.id or False, login=login[:100],
                    detail=str(error.args[0]) if error.args and error.args[0] else False, **values)
            raise
        if uid and uid != SUPERUSER_ID:
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['om.user.audit.log']._om_log('login', user_id=uid, login=login,
                                                 detail=False if interactive else 'API', **values)
                if interactive:
                    env['res.users'].browse(uid)._om_sign_in_mail(values)
        return uid

    def _om_sign_in_mail(self, values):
        """ Tell the user, the administrators or both, as the settings say. """
        params = self.env['ir.config_parameter'].sudo()
        target = params.get_str('om_user_audit.sign_in_mail', 'none')
        if target not in ('user', 'admins', 'both'):
            return
        if params.get_bool('om_user_audit.sign_in_mail_new_only'):
            days = params.get_int('om_user_audit.new_device_days') or 90
            seen = self.env['om.user.audit.log'].sudo().search_count([
                ('user_id', '=', self.id), ('event', '=', 'login'), ('ip', '=', values.get('ip')),
                ('user_agent', '=', values.get('user_agent')),
                ('date', '>', fields.Datetime.now() - timedelta(days=days)),
            ], limit=1)
            if seen:
                return
        recipients = self.env['res.partner']
        if target in ('user', 'both') and self.email:
            recipients |= self.partner_id
        if target in ('admins', 'both'):
            admins = self.env.ref('base.group_system').users.filtered(
                lambda user: user.email and user != self and user.id != SUPERUSER_ID)
            recipients |= admins.partner_id
        if not recipients:
            return
        template = self.env.ref('om_user_audit.mail_template_sign_in', raise_if_not_found=False)
        if not template:
            return
        country = city = False
        if request and request.geoip:
            country = request.geoip.country_name
            city = request.geoip.city.name if request.geoip.city else False
        template.sudo().with_context(
            om_ip=values.get('ip'), om_agent=values.get('user_agent'),
            om_place=', '.join(filter(None, (city, country))),
            om_date=fields.Datetime.now(),
        ).send_mail(self.id, email_values={'recipient_ids': [(6, 0, recipients.ids)]},
                    email_layout_xmlid='mail.mail_notification_light')

    def action_om_audit_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_user_audit.om_user_audit_log_action')
        action['domain'] = [('user_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_om_sessions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_user_audit.om_user_audit_session_action')
        action['domain'] = [('user_id', '=', self.id)]
        return action

    def action_om_end_sessions(self):
        self.env['om.user.audit.session'].sudo().search([('user_id', 'in', self.ids), ('revoked', '=', False)]).action_om_end()
        return True
