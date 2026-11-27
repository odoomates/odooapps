import logging

from odoo import models

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    def _get_trigger_alarm_types(self):
        return super()._get_trigger_alarm_types() + ['om_whatsapp']

    def om_whatsapp_meeting_place(self):
        """ Where the meeting is, or its video call link, as a sentence. """
        self.ensure_one()
        self.check_access('read')
        if self.videocall_location:
            return self.env._("Join here: %(link)s", link=self.videocall_location)
        if self.location:
            return self.env._("Place: %(location)s.", location=self.location)
        return ''

    def _om_whatsapp_reminder_account(self, alarm):
        self.ensure_one()
        if alarm.om_whatsapp_account_id:
            return alarm.om_whatsapp_account_id
        return self.env['om.social.account'].sudo().search([
            ('channel', '=', 'whatsapp'), ('user_ids', 'in', self.user_id.ids), ('company_id', 'in', (self.user_id.company_ids or self.env.company).ids),
        ], limit=1)

    def _do_om_whatsapp_reminder(self, alarms):
        """ Send the WhatsApp reminder to each attendee who has not declined,
        the organizer only when the reminder says so; each message is kept on
        the meeting. """
        for event in self:
            declined = event.attendee_ids.filtered_domain([('state', '=', 'declined')]).partner_id
            for alarm in alarms:
                template = alarm.om_whatsapp_template_id
                account = event._om_whatsapp_reminder_account(alarm)
                if not template or not account:
                    event._message_log(body=self.env._(
                        "The WhatsApp reminder was not sent: set the WhatsApp account of the reminder %(alarm)s.",
                        alarm=alarm.name))
                    continue
                partners = event.partner_ids.filtered(lambda p: p.phone_sanitized and p not in declined)
                if event.user_id and not alarm.notify_responsible:
                    partners -= event.user_id.partner_id
                for partner in partners:
                    event._om_whatsapp_send_to_partner(template, account, partner)

    def _om_whatsapp_send_to_partner(self, template, account, partner):
        """ Send ``template`` to one attendee, with the times in their time
        zone. Never raises: a reminder that cannot go is logged. """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                composer = self.env['om.whatsapp.composer'].sudo().with_context(
                    active_model=self._name, active_ids=self.ids, active_id=self.id,
                    om_whatsapp_tz=partner.tz or False, lang=partner.lang or self.env.lang,
                ).create({
                    'account_id': account.id,
                    'template_id': template.id,
                    'partner_id': partner.id,
                    'number': partner.phone_sanitized,
                })
                messages = composer._post_messages(self.sudo())
                queued = messages._om_social_notifications().filtered(lambda n: n.notification_status == 'ready')
                if queued:
                    account.sudo()._om_social_send_automated(queued)
        except Exception:
            _logger.exception("WhatsApp reminder of %s not sent to %s", self, partner)
