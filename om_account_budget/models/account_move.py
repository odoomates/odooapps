from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class AccountMove(models.Model):
    _inherit = 'account.move'

    budget_warning = fields.Html(
        string='Budget Warning', compute='_compute_budget_warning',
        help='Budget lines this draft vendor bill would push over their planned amount.')

    @api.depends('state', 'move_type', 'date', 'invoice_date', 'company_id',
                 'invoice_line_ids.balance', 'invoice_line_ids.account_id', 'invoice_line_ids.analytic_distribution')
    def _compute_budget_warning(self):
        for move in self:
            overruns = move._get_budget_overruns() if move.state == 'draft' else []
            move.budget_warning = self.env['account.budget.line']._format_budget_overruns(overruns) if overruns else False

    def _get_budget_overruns(self):
        self.ensure_one()
        if not self.is_purchase_document(include_receipts=True) or not self.company_id:
            return []
        date = self.date or self.invoice_date or fields.Date.context_today(self)
        items = [
            {
                'date': date,
                'account': line.account_id,
                'analytic_distribution': line.analytic_distribution,
                'amount': line.balance,
            }
            for line in self.invoice_line_ids if line.display_type == 'product'
        ]
        return self.env['account.budget.line']._get_budget_overruns(self.company_id, items)

    def _post(self, soft=True):
        for move in self:
            if move.company_id.budget_block_documents and move.state == 'draft' \
                    and not self.env.su and not self.env.user.has_group('account.group_account_manager'):
                overruns = move._get_budget_overruns()
                if overruns:
                    raise UserError(_(
                        '%(move)s cannot be posted, it goes over budget:\n%(lines)s\nAsk an accounting manager to post it or '
                        'to raise the budget.',
                        move=move.display_name,
                        lines=self.env['account.budget.line']._format_budget_overruns(overruns, html=False)))
        return super()._post(soft=soft)
