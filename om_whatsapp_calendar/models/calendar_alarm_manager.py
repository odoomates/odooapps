from odoo import api, models


class CalendarAlarm_Manager(models.AbstractModel):
    _inherit = 'calendar.alarm_manager'

    @api.model
    def _send_reminder(self):
        """ The scheduled reminders, and the WhatsApp ones. """
        super()._send_reminder()
        events_by_alarm = self._get_events_by_alarm_to_notify('om_whatsapp')
        if not events_by_alarm:
            return
        all_event_ids = list({event_id for event_ids in events_by_alarm.values() for event_id in event_ids})
        for alarm_id, event_ids in events_by_alarm.items():
            alarm = self.env['calendar.alarm'].browse(alarm_id)
            events = self.env['calendar.event'].browse(event_ids).with_prefetch(all_event_ids)
            events._do_om_whatsapp_reminder(alarm)
            events._setup_event_recurrent_alarms(events_by_alarm)
