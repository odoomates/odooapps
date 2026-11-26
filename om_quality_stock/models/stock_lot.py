from odoo import api, fields, models

LOT_QUALITY_STATES = [
    ('ok', 'OK'),
    ('hold', 'On Hold'),
    ('rejected', 'Rejected'),
]


class StockLot(models.Model):
    _inherit = 'stock.lot'

    om_quality_state = fields.Selection(
        LOT_QUALITY_STATES, string='Quality', default='ok', required=True, tracking=True, copy=False, index=True,
        help="On hold: a quality check failed, the lot waits for a decision. Rejected: scrapped or returned.\n"
             "Lots on hold or rejected are not reserved by Odoo for deliveries and manufacturing.")
    om_quality_check_ids = fields.One2many('om.quality.check', 'lot_id', string='Quality Checks')
    om_quality_check_count = fields.Integer(compute='_compute_om_quality_check_count', string='Quality Checks Count')

    @api.depends('om_quality_check_ids')
    def _compute_om_quality_check_count(self):
        data = dict(self.env['om.quality.check']._read_group(
            [('lot_id', 'in', self.ids), ('state', '!=', 'cancel')], ['lot_id'], ['__count']))
        for lot in self:
            lot.om_quality_check_count = data.get(lot, 0)

    def _om_quality_set_state(self, state, reason=None):
        for lot in self.filtered(lambda lot: lot.om_quality_state != state):
            lot.sudo().om_quality_state = state
            if reason:
                lot.sudo().message_post(body=reason)

    def action_om_quality_hold(self):
        self._om_quality_set_state('hold', self.env._("Put on hold by %s.", self.env.user.name))
        return True

    def action_om_quality_release(self):
        self._om_quality_set_state('ok', self.env._("Released by %s.", self.env.user.name))
        return True

    def action_om_quality_reject(self):
        self._om_quality_set_state('rejected', self.env._("Rejected by %s.", self.env.user.name))
        return True

    def action_om_quality_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_quality.action_om_quality_check')
        action['domain'] = [('lot_id', '=', self.id)]
        action['context'] = {'search_default_filter_not_cancel': 1}
        return action
