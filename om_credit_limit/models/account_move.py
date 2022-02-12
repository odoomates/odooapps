from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_credit = fields.Monetary(related='partner_id.commercial_partner_id.credit', readonly=True)
    partner_credit_limit = fields.Monetary(related='partner_id.credit_limit_compute', readonly=True)
    show_partner_credit_warning = fields.Boolean(compute='_compute_show_partner_credit_warning')

    @api.depends('partner_credit_limit', 'partner_credit',
                 'company_id.account_default_credit_limit', 'company_id.account_credit_limit')
    def _compute_show_partner_credit_warning(self):
        for move in self:
            account_credit_limit = move.company_id.account_credit_limit
            company_limit = move.partner_credit_limit == -1 and move.company_id.account_default_credit_limit
            partner_limit = move.partner_credit_limit > 0 and move.partner_credit_limit
            move.show_partner_credit_warning = account_credit_limit and \
                                               ((company_limit and move.partner_credit > company_limit) or \
                                               (partner_limit and move.partner_credit > partner_limit))


