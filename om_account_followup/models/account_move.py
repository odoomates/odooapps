from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    followup_disputed = fields.Boolean(
        string='Disputed', copy=False, tracking=True,
        help='The customer disputes this invoice: it is left out of the follow-up reminders and of the overdue '
             'amounts until the dispute is settled.')
    followup_dispute_reason = fields.Char(string='Dispute Reason', copy=False, tracking=True)

    def action_followup_dispute(self):
        self.write({'followup_disputed': True})

    def action_followup_undispute(self):
        self.write({'followup_disputed': False, 'followup_dispute_reason': False})


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    followup_line_id = fields.Many2one('followup.line', 'Follow-up Level', copy=False)
    followup_date = fields.Date('Latest Follow-up', copy=False)
    followup_disputed = fields.Boolean(related='move_id.followup_disputed')
    result = fields.Float(compute='_get_result', string="Balance Amount")

    def _get_result(self):
        for aml in self:
            aml.result = aml.debit - aml.credit

    @api.model
    def _followup_open_domain(self, company, partners=None):
        """ The open receivable items the follow-ups remind of: posted, not paid, not disputed """
        domain = [
            ('company_id', '=', company.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
            ('move_id.followup_disputed', '=', False),
            ('partner_id', '!=', False),
        ]
        if partners is not None:
            domain.append(('partner_id', 'in', partners.ids))
        return domain

    def _followup_due_date(self):
        self.ensure_one()
        return self.date_maturity or self.date

    def _followup_age(self, date):
        """ :return: the number of days the item is overdue at `date`, negative when not due yet """
        self.ensure_one()
        return (date - self._followup_due_date()).days
