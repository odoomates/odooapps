from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_audit_weekly_check = fields.Boolean(related='company_id.om_audit_weekly_check', readonly=False)
    om_audit_secure_on_close = fields.Boolean(related='company_id.om_audit_secure_on_close', readonly=False)

    def action_om_secure_all_journals(self):
        self.ensure_one()
        return self.company_id.action_om_secure_all_journals()
