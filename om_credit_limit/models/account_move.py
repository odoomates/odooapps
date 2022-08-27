from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_credit = fields.Monetary(related='partner_id.commercial_partner_id.credit', readonly=True)
    partner_credit_limit = fields.Monetary(related='partner_id.credit_limit_compute', readonly=True)
    show_partner_credit_warning = fields.Boolean(compute='_compute_show_partner_credit_warning')
    credit_limit_type = fields.Selection(related='company_id.credit_limit_type')

    @api.depends('partner_credit_limit', 'partner_credit', 'invoice_line_ids',
                 'company_id.account_default_credit_limit', 'company_id.account_credit_limit')
    def _compute_show_partner_credit_warning(self):
        for move in self:
            account_credit_limit = move.company_id.account_credit_limit
            company_limit = move.partner_credit_limit == -1 and move.company_id.account_default_credit_limit
            partner_limit = move.partner_credit_limit > 0 and move.partner_credit_limit
            partner_credit = move.partner_credit + move.amount_total
            move.show_partner_credit_warning = account_credit_limit and \
                                               ((company_limit and partner_credit > company_limit) or \
                                               (partner_limit and partner_credit > partner_limit))

    def action_post(self):
        result = super(AccountMove, self).action_post()
        for inv in self:
            if inv.show_partner_credit_warning and inv.credit_limit_type == 'block' and \
                    inv.partner_credit > inv.partner_credit_limit:
                raise ValidationError(_("You cannot exceed credit limit ! \n"
                                        "Allowed Limit: %s ! \n"
                                        "Computed Balance: %s !") %(inv.partner_credit_limit, inv.partner_credit))
        return result


