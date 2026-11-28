from odoo import models

# job event: template field of the company
EVENT_TEMPLATES = {
    'planned': 'fs_whatsapp_planned_id',
    'on_the_way': 'fs_whatsapp_on_the_way_id',
    'report': 'fs_whatsapp_report_id',
}


class ProjectTask(models.Model):
    _inherit = 'project.task'

    def _fs_notify_channels(self, event):
        res = super()._fs_notify_channels(event)
        company = self._fs_company()
        template = company[EVENT_TEMPLATES[event]] if event in EVENT_TEMPLATES else False
        if not template or not self.partner_id:
            return res
        if not self._phone_get_recipients_info()[self.id]['sanitized']:
            # no valid WhatsApp number: nothing to send, no failed message on the job
            return res
        messages = self._message_om_whatsapp_template(template.sudo(), account=company.fs_whatsapp_account_id)
        return bool(messages) or res
