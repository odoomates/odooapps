from odoo import api, fields, models


class CalendarAlarm(models.Model):
    _inherit = 'calendar.alarm'

    alarm_type = fields.Selection(selection_add=[('om_whatsapp', 'WhatsApp')], ondelete={'om_whatsapp': 'set default'})
    om_whatsapp_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp Template', domain=[('model', '=', 'calendar.event')],
        compute='_compute_om_whatsapp_template_id', readonly=False, store=True,
        help="The text of the WhatsApp reminder sent to the attendees.")
    om_whatsapp_account_id = fields.Many2one(
        'om.social.account', domain="[('channel', '=', 'whatsapp')]", string='WhatsApp Account',
        help="The account the reminders are sent from. Empty: an account of the organizer of the meeting.")

    @api.depends('alarm_type')
    def _compute_om_whatsapp_template_id(self):
        for alarm in self:
            if alarm.alarm_type == 'om_whatsapp' and not alarm.om_whatsapp_template_id:
                alarm.om_whatsapp_template_id = self.env.ref(
                    'om_whatsapp_calendar.om_whatsapp_template_meeting_reminder', raise_if_not_found=False)
            elif alarm.alarm_type != 'om_whatsapp':
                alarm.om_whatsapp_template_id = False
