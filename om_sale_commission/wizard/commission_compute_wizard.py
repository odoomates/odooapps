from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils


class OmCommissionComputeWizard(models.TransientModel):
    _name = 'om.commission.compute.wizard'
    _description = 'Recompute Commissions'

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return date_utils.start_of(date_utils.start_of(today, 'month') - timedelta(days=1), 'month')

    date_from = fields.Date(string='From', required=True, default=_default_date_from)
    date_to = fields.Date(string='To', required=True, default=fields.Date.context_today)
    plan_ids = fields.Many2many('om.commission.plan', string='Plans',
                                help='Leave empty to recompute every active plan of the company.')

    def action_compute(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._('The start date must come before the end date.'))
        plans = self.plan_ids or self.env['om.commission.plan'].search([('company_id', 'in', self.env.companies.ids)])
        lines = plans._compute_commissions(self.date_from, self.date_to)
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_commission.action_commission_line')
        action['domain'] = [('plan_id', 'in', plans.ids), ('date', '>=', self.date_from)]
        action['context'] = {'search_default_group_user': 1}
        if not lines:
            action['help'] = self.env._('No new commission for these dates.')
        return action
