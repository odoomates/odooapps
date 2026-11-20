from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class ResCompany(models.Model):
    _inherit = 'res.company'

    budget_block_documents = fields.Boolean(
        string='Block Documents Over Budget',
        help="Only the accounting managers can post the vendor bills (and confirm the purchase orders) going over "
             "the planned amount of a budget line; the other users see a warning.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_block_documents = fields.Boolean(related='company_id.budget_block_documents', readonly=False)


class CrossoveredBudgetLines(models.Model):
    _inherit = 'crossovered.budget.lines'

    # a budget line plans a cost as a negative amount: the control below works on costs as positive amounts

    def _get_committed_amount(self):
        """ Expenses already decided but not recorded in the accounting yet (e.g. confirmed purchases), as a
        positive amount. """
        self.ensure_one()
        return 0.0

    def _get_item_amount(self, item):
        """ Part of an expense counted by this budget line.

        :param item: dictionary with date, account (account.account), analytic_distribution (dict), amount
                     (company currency, positive for a cost)
        """
        self.ensure_one()
        if not (self.date_from <= item['date'] <= self.date_to):
            return 0.0
        if self.general_budget_id and item['account'] not in self.general_budget_id.account_ids:
            return 0.0
        if self.analytic_account_id:
            analytic_id = str(self.analytic_account_id.id)
            percent = sum(
                float(share) for key, share in (item.get('analytic_distribution') or {}).items()
                if analytic_id in str(key).split(',')
            )
            return item['amount'] * percent / 100.0
        return item['amount']

    @api.model
    def _get_budget_overruns(self, company, items):
        """ Cost lines of the confirmed and validated budgets that `items` would push over their planned amount.

        :param items: list of dictionaries, see `_get_item_amount`
        :return: list of dictionaries with line, planned, actual, committed, new, over (costs as positive amounts)
        """
        items = [item for item in items if item.get('amount')]
        if not items:
            return []
        dates = [item['date'] for item in items]
        lines = self.search([
            ('company_id', '=', company.id),
            ('crossovered_budget_state', 'in', ('confirm', 'validate')),
            ('planned_amount', '<', 0.0),
            ('date_from', '<=', max(dates)),
            ('date_to', '>=', min(dates)),
        ])
        overruns = []
        for line in lines:
            currency = line.currency_id
            new = currency.round(sum(line._get_item_amount(item) for item in items))
            if currency.compare_amounts(new, 0.0) <= 0:
                continue
            planned, actual = -line.planned_amount, -line.practical_amount
            committed = line._get_committed_amount()
            total = actual + committed + new
            if currency.compare_amounts(total, planned) > 0:
                overruns.append({
                    'line': line,
                    'planned': planned,
                    'actual': actual,
                    'committed': committed,
                    'new': new,
                    'over': currency.round(total - planned),
                })
        return overruns

    @api.model
    def _format_budget_overruns(self, overruns, html=True):
        texts = []
        for overrun in overruns:
            line = overrun['line']
            money = lambda amount: formatLang(self.env, amount, currency_obj=line.currency_id)
            if line.currency_id.is_zero(overrun['committed']):
                text = _('%(line)s: planned %(planned)s, actual %(actual)s, this document %(new)s, '
                         '%(over)s over budget',
                         line=line.name, planned=money(overrun['planned']), actual=money(overrun['actual']),
                         new=money(overrun['new']), over=money(overrun['over']))
            else:
                text = _('%(line)s: planned %(planned)s, actual %(actual)s, committed %(committed)s, '
                         'this document %(new)s, %(over)s over budget',
                         line=line.name, planned=money(overrun['planned']), actual=money(overrun['actual']),
                         committed=money(overrun['committed']), new=money(overrun['new']),
                         over=money(overrun['over']))
            texts.append(text)
        if not html:
            return '\n'.join('- %s' % text for text in texts)
        return Markup('<strong>%s</strong><ul class="mb-0">%s</ul>') % (
            _('This document goes over budget'),
            Markup().join(Markup('<li>%s</li>') % text for text in texts))


class AccountMove(models.Model):
    _inherit = 'account.move'

    budget_warning = fields.Html(
        string='Budget Warning', compute='_compute_budget_warning',
        help='Budget lines this draft vendor bill would push over their planned amount.')

    @api.depends('state', 'move_type', 'date', 'invoice_date', 'company_id',
                 'invoice_line_ids.balance', 'invoice_line_ids.account_id', 'invoice_line_ids.analytic_distribution')
    def _compute_budget_warning(self):
        BudgetLine = self.env['crossovered.budget.lines']
        for move in self:
            overruns = move._get_budget_overruns() if move.state == 'draft' else []
            move.budget_warning = BudgetLine._format_budget_overruns(overruns) if overruns else False

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
        return self.env['crossovered.budget.lines']._get_budget_overruns(self.company_id, items)

    def _post(self, soft=True):
        for move in self:
            if move.company_id.budget_block_documents and move.state == 'draft' \
                    and not self.env.su and not self.env.user.has_group('account.group_account_manager'):
                overruns = move._get_budget_overruns()
                if overruns:
                    raise UserError(_(
                        '%(move)s cannot be posted, it goes over budget:\n%(lines)s\nAsk an accounting manager '
                        'to post it or to raise the budget.',
                        move=move.display_name,
                        lines=self.env['crossovered.budget.lines']._format_budget_overruns(overruns, html=False)))
        return super()._post(soft=soft)
