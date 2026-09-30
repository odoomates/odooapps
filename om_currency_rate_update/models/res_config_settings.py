from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rate_interval = fields.Selection(related='company_id.rate_interval', readonly=False)
    rate_provider = fields.Selection(related='company_id.rate_provider', readonly=False)
    rate_fallback_provider = fields.Selection(related='company_id.rate_fallback_provider', readonly=False)
    rate_openexchangerates_key = fields.Char(
        related='company_id.rate_openexchangerates_key', readonly=False, groups='base.group_system')
    rate_exchangerate_api_key = fields.Char(
        related='company_id.rate_exchangerate_api_key', readonly=False, groups='base.group_system')
    rate_currency_ids = fields.Many2many(related='company_id.rate_currency_ids', readonly=False)
    rate_date_policy = fields.Selection(related='company_id.rate_date_policy', readonly=False)
    rate_max_change = fields.Float(related='company_id.rate_max_change', readonly=False)
    rate_next_date = fields.Date(related='company_id.rate_next_date', readonly=False)
    rate_last_update = fields.Datetime(related='company_id.rate_last_update')
    rate_last_message = fields.Text(related='company_id.rate_last_message')

    def action_update_currency_rates(self):
        self.ensure_one()
        saved = self.company_id.root_id._update_currency_rates()
        return self._rate_notification(self.company_id.root_id.rate_last_message, 'success' if saved else 'warning')

    def action_test_currency_rates(self):
        self.ensure_one()
        return self._rate_notification(self.company_id._test_currency_rates(), 'info')

    def _rate_notification(self, message, notification_type):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Currency Rates'),
                'message': message,
                'type': notification_type,
                'sticky': notification_type == 'warning',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
