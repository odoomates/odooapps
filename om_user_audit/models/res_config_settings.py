from odoo import api, fields, models

from .om_user_audit_rule import DEFAULT_EXCLUDED


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_audit_keep_days = fields.Integer(
        string='Keep the Logs (days)', config_parameter='om_user_audit.keep_days', default=90,
        help="Older lines are deleted every night. 0 keeps them forever.")
    om_audit_keep_sign_in_days = fields.Integer(
        string='Keep the Sign-ins (days)', config_parameter='om_user_audit.keep_sign_in_days',
        help="Sign-ins, sign-outs and ended sessions. Left at 0, they follow the logs.")
    om_audit_log_reads = fields.Boolean(
        string='Log Reads', default=True,
        help="Reads are the most frequent event: turn them off everywhere at once when the "
             "logs grow too fast.")
    om_audit_excluded_models = fields.Char(
        string='Never Logged',
        help="Technical data never logged when no rule names it: technical names separated by "
             "commas, * for any part (ir.*, bus.*). Left empty, the default list applies.")
    om_audit_sign_in_mail = fields.Selection(
        [('none', 'Nobody'), ('user', 'The user'), ('admins', 'The administrators'), ('both', 'Both')],
        string='Sign-in Emails To', config_parameter='om_user_audit.sign_in_mail', default='none')
    om_audit_sign_in_mail_new_only = fields.Boolean(
        string='Only From a New Device', config_parameter='om_user_audit.sign_in_mail_new_only',
        help="Only when the user signs in from an address and a browser not seen for 90 days.")
    om_audit_idle_minutes = fields.Integer(
        string='End Idle Sessions After (minutes)', config_parameter='om_user_audit.idle_minutes',
        help="A session without a request for this long is ended. 0 never ends one.")
    om_audit_lines_today = fields.Integer(string='Lines in the Last 24 Hours',
                                          compute='_compute_om_audit_lines_today')

    def _compute_om_audit_lines_today(self):
        count = self.env['om.user.audit.log'].sudo()._om_lines_per_day()
        for settings in self:
            settings.om_audit_lines_today = count

    @api.model
    def get_values(self):
        values = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        values['om_audit_log_reads'] = params.get_bool('om_user_audit.log_reads', True)
        values['om_audit_excluded_models'] = (params.get_str('om_user_audit.excluded_models')
                                              or ', '.join(DEFAULT_EXCLUDED))
        return values

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_bool('om_user_audit.log_reads', self.om_audit_log_reads)
        params.set_str('om_user_audit.excluded_models', self.om_audit_excluded_models or False)
