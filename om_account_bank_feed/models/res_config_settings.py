from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bank_feed_reminder_days = fields.Integer(related='company_id.bank_feed_reminder_days', readonly=False)
    bank_feed_sync_interval = fields.Integer(
        string='Sync Every (Hours)', compute='_compute_bank_feed_sync_interval', readonly=False,
        help="How often the bank feeds fetch the new transactions.")

    @api.depends('company_id')
    def _compute_bank_feed_sync_interval(self):
        cron = self.env.ref('om_account_bank_feed.ir_cron_bank_feed_sync', raise_if_not_found=False)
        interval = 4
        if cron:
            cron = cron.sudo()
            interval = cron.interval_number * {'minutes': 1 / 60, 'hours': 1, 'days': 24, 'weeks': 168,
                                               'months': 720}.get(cron.interval_type, 1)
        for settings in self:
            settings.bank_feed_sync_interval = max(int(interval), 1)

    def set_values(self):
        super().set_values()
        cron = self.env.ref('om_account_bank_feed.ir_cron_bank_feed_sync', raise_if_not_found=False)
        if not cron or self.bank_feed_sync_interval <= 0:
            return
        cron = cron.sudo()
        if (cron.interval_number, cron.interval_type) != (self.bank_feed_sync_interval, 'hours'):
            cron.write({'interval_number': self.bank_feed_sync_interval, 'interval_type': 'hours'})
