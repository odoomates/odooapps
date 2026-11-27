from odoo import fields, models

from odoo.addons.om_sale_commission.models.commission_plan import PERIOD_MONTHS


class OmCommissionPlan(models.Model):
    _inherit = 'om.commission.plan'

    subscription_base = fields.Selection([
        ('invoice', 'Invoiced Amount'),
        ('mrr', 'Monthly Recurring Revenue'),
        ('new_mrr', 'New MRR'),
    ], string='Subscription Commission On', required=True, default='invoice',
        help='Invoiced Amount: the recurring lines of subscriptions count like any other invoice or order line. '
             'Monthly Recurring Revenue: the MRR of the running subscriptions, for each month of the period. '
             'New MRR: the MRR added in the period by new subscriptions and upsells.')
    subscription_recurrence = fields.Selection([
        ('recurring', 'Every Period'),
        ('first', 'First Period Only'),
    ], string='Pay Subscriptions', required=True, default='recurring',
        help='First Period Only: only the first invoice of a subscription, or the MRR of its first month, '
             'earns a commission.')
    subscription_only = fields.Boolean(
        string='Subscriptions Only', help='Only subscriptions earn a commission with this plan.')

    def _get_commission_sources(self, date_from, date_to):
        sources = super()._get_commission_sources(date_from, date_to)
        if self.subscription_base == 'invoice':
            if self.subscription_recurrence == 'first' and self.base == 'invoice':
                sources = [s for s in sources if not self._is_subscription_source(s)
                           or self._is_first_subscription_invoice(s)]
            if self.subscription_only:
                sources = [s for s in sources if self._is_subscription_source(s)]
            return sources
        sources = [] if self.subscription_only else [s for s in sources if not self._is_subscription_source(s)]
        if self.subscription_base == 'mrr':
            return sources + self._get_mrr_sources(date_from, date_to)
        return sources + self._get_new_mrr_sources(date_from, date_to)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _get_source_record(self, source):
        model, __, record_id = source['key'].partition(',')
        if model == 'aml':
            return self.env['account.move.line'].browse(int(record_id))
        if model == 'sol':
            return self.env['sale.order.line'].browse(int(record_id))
        return None

    def _get_source_subscription(self, source):
        """The subscription of a recurring invoice or order line source, else an empty recordset."""
        record = self._get_source_record(source)
        orders = self.env['sale.order']
        if record is None:
            return orders
        sale_lines = record.sale_line_ids if record._name == 'account.move.line' else record
        sale_lines = sale_lines.filtered('subscription_recurring')
        if not sale_lines:
            return orders
        if record._name == 'account.move.line' and record.move_id.subscription_id:
            return record.move_id.subscription_id
        order = sale_lines[:1].order_id
        return order.subscription_parent_id if order.subscription_type == 'upsell' else order

    def _is_subscription_source(self, source):
        return bool(self._get_source_subscription(source))

    def _is_first_subscription_invoice(self, source):
        subscription = self._get_source_subscription(source)
        move = source['move']
        if not subscription or not move:
            return True
        first = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            '|',
            ('subscription_id', '=', subscription.id),
            ('invoice_line_ids.sale_line_ids.order_id', '=', subscription.id),
        ], order='invoice_date, id', limit=1)
        return move == first or (move.move_type == 'out_refund' and move.reversed_entry_id == first)

    def _get_subscription_product(self, order):
        return order.order_line.filtered('subscription_recurring')[:1].product_id

    def _prepare_subscription_source(self, key, date, order, revenue, user=None, team=None):
        return {
            'key': key,
            'date': date,
            'name': f'{order.name} - {order.partner_id.display_name}',
            'user': user if user is not None else order.user_id,
            'team': team if team is not None else order.team_id,
            'referrer': order.om_referrer_id,
            'customer': order.partner_id.commercial_partner_id,
            'product': self._get_subscription_product(order),
            'quantity': 1.0,
            'revenue': revenue,
            'cost': 0.0,
            'move': self.env['account.move'],
            'order': order,
            'reversed_move': self.env['account.move'],
        }

    def _get_mrr_sources(self, date_from, date_to):
        """MRR of the subscriptions running at the end of the period, for each month of the period; with
        First Period Only, one month of MRR in the period the subscription starts."""
        self.ensure_one()
        company = self.company_id
        domain = [
            ('company_id', '=', company.id),
            ('is_subscription', '=', True),
            ('state', '=', 'sale'),
            ('subscription_start_date', '<=', date_to),
        ]
        if self.subscription_recurrence == 'first':
            domain.append(('subscription_start_date', '>=', date_from))
        sources = []
        for order in self.env['sale.order'].search(domain):
            logs = order.subscription_log_ids.filtered(lambda log: log.event_date <= date_to)
            last = logs.sorted(lambda log: (log.event_date, log.id))[-1:] if logs else logs
            mrr = last.recurring_monthly if last else 0.0
            if self.subscription_recurrence == 'first' and not mrr:
                mrr = order.subscription_mrr
            if order.currency_id.is_zero(mrr):
                continue
            months = 1 if self.subscription_recurrence == 'first' else PERIOD_MONTHS[self.period]
            revenue = order.currency_id._convert(mrr * months, company.currency_id, company, date_to)
            date = order.subscription_start_date if self.subscription_recurrence == 'first' else date_to
            sources.append(self._prepare_subscription_source(
                f'submrr,{order.id},{date_from}', date, order, revenue))
        return sources

    def _get_new_mrr_sources(self, date_from, date_to):
        """MRR added in the period by new subscriptions and expansions (upsells)."""
        self.ensure_one()
        company = self.company_id
        logs = self.env['om.subscription.log'].search([
            ('company_id', '=', company.id),
            ('event_type', 'in', ('new', 'expansion')),
            ('event_date', '>=', date_from),
            ('event_date', '<=', date_to),
        ])
        sources = []
        for log in logs:
            revenue = log.currency_id._convert(log.amount_signed, company.currency_id, company, log.event_date)
            sources.append(self._prepare_subscription_source(
                f'sublog,{log.id}', log.event_date, log.order_id, revenue, user=log.user_id, team=log.team_id))
        return sources
