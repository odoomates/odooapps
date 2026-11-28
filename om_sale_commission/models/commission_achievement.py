from odoo import api, fields, models


class OmCommissionAchievement(models.Model):
    _name = 'om.commission.achievement'
    _description = 'Commission Achievement'
    _order = 'period_start desc, plan_id, id'
    _rec_name = 'plan_id'

    plan_id = fields.Many2one('om.commission.plan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', string='Salesperson', index='btree_not_null')
    team_id = fields.Many2one('crm.team', string='Sales Team', index='btree_not_null')
    partner_id = fields.Many2one('res.partner', string='Reseller', index='btree_not_null')
    holder_name = fields.Char(string='For', compute='_compute_holder_name')
    period_start = fields.Date(string='Period', required=True, index=True)
    period_end = fields.Date(string='Period End', required=True)
    revenue = fields.Monetary()
    margin = fields.Monetary()
    target_amount = fields.Monetary(string='Target')
    achievement = fields.Float(string='Achievement (%)', digits=(16, 1), aggregator='avg')
    rate = fields.Float(string='Tier Rate (%)', digits=(16, 2), aggregator=None)
    commission = fields.Monetary()

    @api.depends('user_id', 'team_id', 'partner_id')
    def _compute_holder_name(self):
        for record in self:
            record.holder_name = (record.user_id or record.team_id or record.partner_id).display_name
