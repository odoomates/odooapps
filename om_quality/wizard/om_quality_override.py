from odoo import fields, models


class OmQualityOverride(models.TransientModel):
    _name = 'om.quality.override'
    _description = 'Override Blocking Quality Checks'

    check_ids = fields.Many2many('om.quality.check', string='Checks', required=True)
    reason = fields.Text(required=True, help="Why the document may go on without these checks. Logged on the checks and the document.")

    def action_confirm(self):
        self.ensure_one()
        self.check_ids._do_override(self.reason)
        return {'type': 'ir.actions.act_window_close'}
