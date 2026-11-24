import logging

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_date

_logger = logging.getLogger(__name__)

SUBSCRIPTION_STATES = [
    ('draft', 'Quotation'),
    ('progress', 'In Progress'),
    ('paused', 'Paused'),
    ('renewed', 'Renewed'),
    ('churn', 'Closed'),
]
ACTIVE_STATES = ('progress', 'paused')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    subscription_plan_id = fields.Many2one(
        'om.subscription.plan', string='Recurring Plan', compute='_compute_subscription_plan_id', store=True,
        readonly=False, precompute=True, index='btree_not_null', tracking=True, check_company=True,
        help='Confirming a quotation with a recurring plan starts a subscription: its subscription products '
             'are invoiced every period of the plan.')
    subscription_type = fields.Selection([
        ('new', 'New'),
        ('upsell', 'Upsell'),
        ('renewal', 'Renewal'),
    ], default='new', copy=False)
    is_subscription = fields.Boolean(string='Is a Subscription', compute='_compute_is_subscription', store=True,
                                     index=True)
    subscription_state = fields.Selection(
        SUBSCRIPTION_STATES, string='Subscription Status', compute='_compute_subscription_state', store=True,
        readonly=False, copy=False, tracking=True, index=True, group_expand=True)
    subscription_parent_id = fields.Many2one('sale.order', string='Original Subscription', copy=False,
                                             index='btree_not_null', readonly=True)
    subscription_child_ids = fields.One2many('sale.order', 'subscription_parent_id', string='Upsells and Renewals')
    subscription_child_count = fields.Integer(compute='_compute_subscription_child_count')
    subscription_start_date = fields.Date(string='Start Date', copy=False, tracking=True)
    subscription_next_invoice_date = fields.Date(string='Next Invoice', copy=False, tracking=True, index=True)
    subscription_end_date = fields.Date(string='End Date', copy=False, tracking=True,
                                        help='Last day of the subscription. Leave empty to run until closed.')
    subscription_recurring_total = fields.Monetary(
        string='Recurring Total', compute='_compute_subscription_recurring', store=True,
        help='Untaxed amount invoiced every period.')
    subscription_mrr = fields.Monetary(
        string='Monthly Recurring Revenue', compute='_compute_subscription_recurring', store=True)
    subscription_arr = fields.Monetary(
        string='Annual Recurring Revenue', compute='_compute_subscription_recurring', store=True)
    subscription_close_reason_id = fields.Many2one('om.subscription.close.reason', string='Close Reason',
                                                   copy=False, tracking=True)
    subscription_close_date = fields.Date(string='Closed On', copy=False)
    subscription_health = fields.Selection([
        ('normal', 'Neutral'),
        ('done', 'Good'),
        ('blocked', 'At Risk'),
    ], string='Health', default='normal', copy=False, tracking=True)
    subscription_token_id = fields.Many2one(
        'payment.token', string='Saved Payment Method', copy=False, tracking=True,
        domain="[('partner_id', 'child_of', commercial_partner_id)]",
        help='Charged automatically for each new invoice of the subscription.')
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id')
    subscription_payment_failed_count = fields.Integer(string='Failed Payments', copy=False)
    subscription_payment_retry_date = fields.Date(string='Next Payment Retry', copy=False)
    subscription_log_ids = fields.One2many('om.subscription.log', 'order_id', string='MRR History')
    subscription_prorate_ratio = fields.Float(string='Prorated Share', digits=(16, 4), default=1.0, copy=False)
    subscription_prorate_start = fields.Date(string='Prorated From', copy=False)
    subscription_prorate_end = fields.Date(string='Prorated To', copy=False)
    subscription_invoice_ids = fields.One2many('account.move', 'subscription_id', string='Recurring Invoices')

    # ------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------

    @api.depends('sale_order_template_id')
    def _compute_subscription_plan_id(self):
        default_plan = self.env['om.subscription.plan']
        if self.env.context.get('subscription_default_plan'):
            default_plan = default_plan.search([], limit=1)
        for order in self:
            plan = order.sale_order_template_id.subscription_plan_id
            if plan and order.state in ('draft', 'sent'):
                order.subscription_plan_id = plan
            elif not order.subscription_plan_id and not order.id and default_plan:
                order.subscription_plan_id = default_plan

    @api.depends('subscription_plan_id', 'subscription_type')
    def _compute_is_subscription(self):
        for order in self:
            order.is_subscription = bool(order.subscription_plan_id) and order.subscription_type != 'upsell'

    @api.depends('is_subscription', 'state')
    def _compute_subscription_state(self):
        for order in self:
            if not order.is_subscription or order.state == 'cancel':
                order.subscription_state = False
            elif order.state in ('draft', 'sent'):
                order.subscription_state = 'draft'
            elif order.subscription_state in (False, 'draft'):
                order.subscription_state = 'progress'

    def _compute_subscription_child_count(self):
        data = dict(self.env['sale.order']._read_group(
            [('subscription_parent_id', 'in', self.ids)], ['subscription_parent_id'], ['__count']))
        for order in self:
            order.subscription_child_count = data.get(order, 0)

    @api.depends('order_line.price_subtotal', 'order_line.subscription_recurring', 'subscription_plan_id',
                 'is_subscription')
    def _compute_subscription_recurring(self):
        for order in self:
            if not order.is_subscription:
                order.subscription_recurring_total = order.subscription_mrr = order.subscription_arr = 0.0
                continue
            total = sum(order.order_line.filtered('subscription_recurring').mapped('price_subtotal'))
            mrr = order.currency_id.round(total * order.subscription_plan_id._get_monthly_factor())
            order.subscription_recurring_total = total
            order.subscription_mrr = mrr
            order.subscription_arr = mrr * 12

    @api.onchange('subscription_plan_id')
    def _onchange_subscription_plan_id(self):
        if self.order_line and self.state in ('draft', 'sent'):
            self._recompute_prices()

    # ------------------------------------------------------------
    # Sale overrides
    # ------------------------------------------------------------

    def _confirmation_error_message(self):
        message = super()._confirmation_error_message()
        if not message and self.is_subscription and not self.order_line.filtered('subscription_recurring'):
            message = self.env._(
                'Add at least one subscription product to %(order)s before confirming it, or remove its '
                'recurring plan.', order=self.name)
        return message

    def action_confirm(self):
        # Upsell lines left at zero only list the current quantities: drop them.
        self.filtered(lambda o: o.subscription_type == 'upsell').order_line.filtered(
            lambda line: not line.display_type and line.product_id and not line.product_uom_qty
        ).unlink()
        return super().action_confirm()

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            if order.subscription_type == 'upsell' and order.subscription_parent_id:
                order._subscription_apply_upsell()
            elif order.is_subscription:
                order._subscription_start()
        return res

    def _should_be_locked(self):
        if self.subscription_plan_id:
            return False
        return super()._should_be_locked()

    def _action_cancel(self):
        res = super()._action_cancel()
        self.filtered('is_subscription')._subscription_sync_log()
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals:
            self.filtered(lambda o: o.subscription_state in ACTIVE_STATES)._subscription_sync_log()
        return res

    def _get_invoiceable_lines(self, final=False):
        # Recurring lines are invoiced period by period by the subscription, never by the standard flow.
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda line: not line.subscription_recurring)

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        if self.subscription_type == 'upsell' and self.subscription_parent_id:
            values['subscription_id'] = self.subscription_parent_id.id
        return values

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------

    def _subscription_start(self):
        self.ensure_one()
        plan = self.subscription_plan_id
        start = self.subscription_start_date or fields.Date.context_today(self)
        vals = {
            'subscription_start_date': start,
            'subscription_state': 'progress',
            'subscription_next_invoice_date': start if plan.invoice_in_advance else start + plan._get_billing_delta(),
        }
        duration = plan._get_duration_delta()
        if duration and not self.subscription_end_date:
            vals['subscription_end_date'] = start + duration
        self.write(vals)
        if self.subscription_type == 'renewal' and self.subscription_parent_id:
            self.subscription_parent_id._subscription_mark_renewed(self)
        self._subscription_sync_log(event_date=start)

    def _subscription_mark_renewed(self, renewal):
        for order in self:
            order.write({
                'subscription_state': 'renewed',
                'subscription_end_date': renewal.subscription_start_date,
                'subscription_close_date': renewal.subscription_start_date,
            })
            order.message_post(body=self.env._('Renewed by %(order)s.', order=renewal._get_html_link()))
            order._subscription_sync_log(event_date=renewal.subscription_start_date)

    def _subscription_apply_upsell(self):
        self.ensure_one()
        parent = self.subscription_parent_id
        for line in self.order_line.filtered(
            lambda l: not l.display_type and l.product_id.is_subscription_product and l.product_uom_qty
        ):
            parent_line = line.subscription_parent_line_id.filtered(lambda pl: pl.order_id == parent)
            if not parent_line:
                parent_line = parent.order_line.filtered(
                    lambda pl, line=line: pl.product_id == line.product_id and pl.subscription_recurring
                    and pl.product_uom_id == line.product_uom_id)[:1]
            if parent_line:
                parent_line.product_uom_qty += line.product_uom_qty
            else:
                parent.order_line = [Command.create({
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom_id': line.product_uom_id.id,
                })]
        parent.message_post(body=self.env._('Upsell %(order)s confirmed.', order=self._get_html_link()))
        parent._subscription_sync_log()

    def _subscription_sync_log(self, event_date=None, close_reason=False):
        """Log the change of MRR since the last log, to follow new, expansion, contraction and churn."""
        today = fields.Date.context_today(self)
        logs = self.env['om.subscription.log']
        for order in self.filtered('subscription_plan_id'):
            if order.subscription_type == 'upsell':
                continue
            currency = order.currency_id
            target = order.subscription_mrr if order.subscription_state in ACTIVE_STATES else 0.0
            current = sum(order.subscription_log_ids.mapped('amount_signed'))
            diff = currency.round(target - current)
            if currency.is_zero(diff):
                continue
            date = event_date or today
            values = {
                'order_id': order.id,
                'event_date': date,
                'currency_id': currency.id,
                'company_id': order.company_id.id,
                'partner_id': order.partner_id.id,
                'plan_id': order.subscription_plan_id.id,
                'user_id': order.user_id.id,
                'team_id': order.team_id.id,
            }
            vals_list = []
            if (not order.subscription_log_ids and order.subscription_type == 'renewal'
                    and order.subscription_parent_id):
                transferred = currency.round(min(order.subscription_parent_id.subscription_mrr, target))
                if not currency.is_zero(transferred):
                    vals_list.append({**values, 'event_type': 'transfer', 'amount_signed': transferred,
                                      'recurring_monthly': transferred})
                    current, diff = transferred, currency.round(target - transferred)
            if not currency.is_zero(diff):
                if currency.is_zero(target):
                    event_type = 'transfer' if order.subscription_state == 'renewed' else 'churn'
                elif currency.is_zero(current):
                    event_type = 'new'
                else:
                    event_type = 'expansion' if diff > 0 else 'contraction'
                vals_list.append({
                    **values,
                    'event_type': event_type,
                    'amount_signed': diff,
                    'recurring_monthly': target,
                    'close_reason_id': close_reason.id if close_reason and event_type == 'churn' else False,
                })
            logs |= logs.create(vals_list)
        return logs

    def _subscription_check_state(self, states):
        for order in self:
            if not order.is_subscription or order.subscription_state not in states:
                raise UserError(self.env._('This action is not available for %(order)s in its current status.',
                                           order=order.name))

    def action_subscription_pause(self):
        self._subscription_check_state(('progress',))
        self.subscription_state = 'paused'
        return True

    def action_subscription_resume(self):
        self._subscription_check_state(('paused',))
        today = fields.Date.context_today(self)
        for order in self:
            order.write({
                'subscription_state': 'progress',
                'subscription_next_invoice_date': max(order.subscription_next_invoice_date or today, today),
            })
        return True

    def action_subscription_close(self):
        self._subscription_check_state(ACTIVE_STATES)
        return {
            'name': self.env._('Close Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'om.subscription.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_ids': self.ids},
        }

    def _subscription_close(self, reason=False, note=False, send_mail=True):
        today = fields.Date.context_today(self)
        for order in self:
            order.write({
                'subscription_state': 'churn',
                'subscription_close_reason_id': reason.id if reason else False,
                'subscription_close_date': today,
                'subscription_end_date': min(order.subscription_end_date or today, today),
                'subscription_payment_retry_date': False,
            })
            order.subscription_child_ids.filtered(lambda o: o.state in ('draft', 'sent'))._action_cancel()
            order._subscription_sync_log(event_date=today, close_reason=reason)
            body = self.env._('Subscription closed: %(reason)s', reason=reason.name if reason else '-')
            if note:
                body = Markup('%s<br/>%s') % (body, note)
            order.message_post(body=body)
            if send_mail:
                order._subscription_send_mail('om_sale_subscription.mail_template_subscription_close')
        return True

    def action_subscription_reopen(self):
        self._subscription_check_state(('churn',))
        today = fields.Date.context_today(self)
        for order in self:
            end = order.subscription_end_date
            order.write({
                'subscription_state': 'progress',
                'subscription_close_reason_id': False,
                'subscription_close_date': False,
                'subscription_end_date': end if end and end > today else False,
                'subscription_next_invoice_date': max(order.subscription_next_invoice_date or today, today),
            })
            order._subscription_sync_log(event_date=today)
        return True

    def _subscription_new_order_values(self, subscription_type):
        self.ensure_one()
        return {
            'partner_id': self.partner_id.id,
            'partner_invoice_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'pricelist_id': self.pricelist_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'payment_term_id': self.payment_term_id.id,
            'company_id': self.company_id.id,
            'user_id': self.user_id.id,
            'team_id': self.team_id.id,
            'origin': self.name,
            'client_order_ref': self.client_order_ref,
            'subscription_plan_id': self.subscription_plan_id.id,
            'subscription_type': subscription_type,
            'subscription_parent_id': self.id,
            'subscription_token_id': self.subscription_token_id.id,
            'tag_ids': [Command.set(self.tag_ids.ids)],
        }

    def _subscription_prorate_values(self, date):
        """Share of the current period left after `date`, for upsells invoiced until the next invoice."""
        self.ensure_one()
        plan = self.subscription_plan_id
        period_end = self.subscription_next_invoice_date
        if not plan.invoice_in_advance or not period_end or period_end <= date:
            # Periods invoiced at their end already include the new quantities at the next invoice.
            return {'subscription_prorate_ratio': 0.0}
        period_start = max(period_end - plan._get_billing_delta(), self.subscription_start_date or date)
        total_days = (period_end - period_start).days or 1
        ratio = min(max((period_end - date).days / total_days, 0.0), 1.0)
        return {
            'subscription_prorate_ratio': round(ratio, 4),
            'subscription_prorate_start': date,
            'subscription_prorate_end': period_end - relativedelta(days=1),
        }

    def action_subscription_upsell(self):
        self._subscription_check_state(('progress',))
        self.ensure_one()
        today = fields.Date.context_today(self)
        values = self._subscription_new_order_values('upsell')
        values.update(self._subscription_prorate_values(today))
        values['order_line'] = [Command.create({
            'product_id': line.product_id.id,
            'product_uom_qty': 0.0,
            'product_uom_id': line.product_uom_id.id,
            'subscription_parent_line_id': line.id,
            'sequence': line.sequence,
        }) for line in self.order_line.filtered('subscription_recurring')]
        upsell = self.create(values)
        return upsell._get_formview_action()

    def action_subscription_renew(self):
        self._subscription_check_state(ACTIVE_STATES)
        self.ensure_one()
        renewal = self._subscription_create_renewal()
        return renewal._get_formview_action()

    def _subscription_create_renewal(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        values = self._subscription_new_order_values('renewal')
        values['subscription_start_date'] = max(
            self.subscription_end_date or self.subscription_next_invoice_date or today, today)
        values['order_line'] = [Command.create({
            'product_id': line.product_id.id,
            'product_uom_qty': line.product_uom_qty,
            'product_uom_id': line.product_uom_id.id,
            'discount': line.discount,
            'sequence': line.sequence,
        }) for line in self.order_line.filtered('subscription_recurring')]
        renewal = self.create(values)
        self.message_post(body=self.env._('Renewal quotation %(order)s created.', order=renewal._get_html_link()))
        return renewal

    def _get_formview_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_open_subscription_children(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        action.update({
            'name': self.env._('Upsells and Renewals'),
            'domain': [('subscription_parent_id', '=', self.id)],
            'context': {'create': False},
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
        })
        return action

    def action_open_subscription_parent(self):
        self.ensure_one()
        return self.subscription_parent_id._get_formview_action()

    def action_open_subscription_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_subscription.action_subscription_log')
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'search_default_group_by_date': False}
        action['view_mode'] = 'list,pivot,graph'
        action['views'] = [(False, 'list'), (False, 'pivot'), (False, 'graph')]
        return action

    # ------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------

    def _subscription_get_period(self):
        self.ensure_one()
        plan = self.subscription_plan_id
        delta = plan._get_billing_delta()
        next_date = self.subscription_next_invoice_date
        start = next_date if plan.invoice_in_advance else next_date - delta
        if self.subscription_start_date and start < self.subscription_start_date:
            start = self.subscription_start_date
        end = (next_date + delta if plan.invoice_in_advance else next_date) - relativedelta(days=1)
        if self.subscription_end_date and end >= self.subscription_end_date:
            end = self.subscription_end_date - relativedelta(days=1)
        return start, end

    def _subscription_is_due(self, date):
        self.ensure_one()
        next_date = self.subscription_next_invoice_date
        if not next_date or next_date > date:
            return False
        if self.subscription_state == 'progress':
            limit = self.subscription_end_date
        elif self.subscription_state == 'renewed':
            limit = self.subscription_end_date or next_date
        else:
            return False
        if not limit:
            return True
        start = next_date if self.subscription_plan_id.invoice_in_advance else (
            next_date - self.subscription_plan_id._get_billing_delta())
        return start < limit

    def _subscription_prepare_invoice(self):
        self.ensure_one()
        start, end = self._subscription_get_period()
        lang = self.partner_invoice_id.lang or self.env.lang
        period_text = self.env._(
            '%(start)s to %(end)s',
            start=format_date(self.env, start, lang_code=lang),
            end=format_date(self.env, end, lang_code=lang),
        )
        line_commands = []
        for line in self.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment):
            if line.subscription_recurring:
                if not line.product_uom_qty:
                    continue
                line_commands.append(Command.create(line._prepare_invoice_line(
                    quantity=line.product_uom_qty,
                    name='\n'.join(part for part in (line.name, period_text) if part),
                )))
            elif line.qty_to_invoice > 0:
                line_commands.append(Command.create(line._prepare_invoice_line()))
        if not line_commands:
            return False
        values = self._prepare_invoice()
        values.update({
            'subscription_id': self.id,
            'subscription_period_start': start,
            'subscription_period_end': end,
            'invoice_line_ids': line_commands,
        })
        return values

    def _subscription_create_invoices(self):
        """Create the invoice of the next period of each subscription and move to the following period."""
        invoices = self.env['account.move']
        for order in self:
            values = order._subscription_prepare_invoice()
            if not values:
                continue
            invoice = order._create_account_invoices([values])
            order.subscription_next_invoice_date += order.subscription_plan_id._get_billing_delta()
            order.message_post(body=self.env._('Invoice %(invoice)s created for %(start)s to %(end)s.',
                                               invoice=invoice._get_html_link(),
                                               start=format_date(self.env, values['subscription_period_start']),
                                               end=format_date(self.env, values['subscription_period_end'])))
            invoices |= invoice
        return invoices

    def action_subscription_generate_invoice(self):
        self._subscription_check_state(('progress',))
        for order in self:
            if order.subscription_end_date and order.subscription_next_invoice_date >= order.subscription_end_date \
                    and order.subscription_plan_id.invoice_in_advance:
                raise UserError(self.env._('%(order)s has no period left to invoice before its end date.',
                                           order=order.name))
        invoices = self._subscription_create_invoices()
        if not invoices:
            raise UserError(self.env._('There is nothing to invoice: the recurring lines have no quantity.'))
        return self.action_view_invoice(invoices=invoices)

    def _subscription_after_invoice_post(self, invoice):
        """Send a posted invoice of the subscription, use its online payments and charge the saved card."""
        self.ensure_one()
        template = self.env.ref('om_sale_subscription.mail_template_subscription_invoice', raise_if_not_found=False)
        try:
            with self.env.cr.savepoint():
                self.env['account.move.send']._generate_and_send_invoices(
                    invoice, allow_raising=False, allow_fallback_pdf=True, sending_methods=['email'],
                    mail_template=template)
        except Exception:  # noqa: BLE001
            _logger.exception('Could not send the invoice %s of subscription %s', invoice.name, self.name)
        self._subscription_reconcile_payments(invoice)
        if self.subscription_token_id:
            self._subscription_charge_invoice(invoice)

    def _subscription_reconcile_payments(self, invoice):
        """Use the payments made online on the subscription order (not reconciled yet) for `invoice`."""
        self.ensure_one()
        payments = self.sudo().transaction_ids.filtered(lambda tx: tx.state == 'done').payment_id
        lines = payments.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
            and line.partner_id.commercial_partner_id == invoice.commercial_partner_id)
        for line in lines:
            if invoice.payment_state not in ('not_paid', 'partial'):
                break
            invoice.js_assign_outstanding_line(line.id)

    def _subscription_charge_invoice(self, invoice):
        """Charge the saved payment method of the subscription for `invoice`."""
        self.ensure_one()
        token = self.subscription_token_id.sudo()
        if not token.active or invoice.state != 'posted' or invoice.payment_state not in ('not_paid', 'partial'):
            return self.env['payment.transaction']
        pending = invoice.sudo().transaction_ids.filtered(lambda tx: tx.state in ('draft', 'pending', 'authorized'))
        if pending:
            return self.env['payment.transaction']
        TX = self.env['payment.transaction'].sudo()
        tx = TX.create({
            'provider_id': token.provider_id.id,
            'payment_method_id': token.payment_method_id.id,
            'reference': TX._compute_reference(token.provider_id.code, prefix=invoice.name),
            'amount': invoice.amount_residual,
            'currency_id': invoice.currency_id.id,
            'partner_id': token.partner_id.id,
            'token_id': token.id,
            'operation': 'offline',
            'invoice_ids': [Command.set(invoice.ids)],
            'subscription_id': self.id,
        })
        tx._charge_with_token()
        return tx

    def _subscription_payment_succeeded(self, tx):
        for order in self:
            was_failing = order.subscription_payment_failed_count
            order.write({
                'subscription_payment_failed_count': 0,
                'subscription_payment_retry_date': False,
                'subscription_health': 'normal' if order.subscription_health == 'blocked' else order.subscription_health,
            })
            if was_failing:
                order.message_post(body=self.env._('Payment %(ref)s succeeded.', ref=tx.reference))

    def _subscription_payment_failed(self, tx):
        today = fields.Date.context_today(self)
        for order in self:
            plan = order.subscription_plan_id
            count = order.subscription_payment_failed_count + 1
            retry_date = False
            if count <= plan.payment_retry_count:
                retry_date = today + relativedelta(days=max(plan.payment_retry_interval, 1))
            order.write({
                'subscription_payment_failed_count': count,
                'subscription_payment_retry_date': retry_date,
                'subscription_health': 'blocked',
            })
            order.message_post(body=self.env._('Payment %(ref)s failed: %(message)s', ref=tx.reference,
                                               message=tx.state_message or tx.state))
            order._subscription_send_mail('om_sale_subscription.mail_template_subscription_payment_failure')

    def _subscription_unpaid_invoices(self):
        return self.env['account.move'].sudo().search([
            ('subscription_id', 'in', self.ids),
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ], order='invoice_date_due, id')

    def _subscription_send_mail(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return
        for order in self:
            order.with_user(SUPERUSER_ID).with_context(force_send=True).message_post_with_source(
                template,
                email_layout_xmlid='mail.mail_notification_light',
                subtype_xmlid='mail.mt_comment',
            )

    # ------------------------------------------------------------
    # Scheduled action
    # ------------------------------------------------------------

    @api.model
    def _cron_subscription_process(self):
        today = fields.Date.context_today(self)
        self._subscription_process_end_of_term(today)
        self._subscription_process_invoices(today)
        self._subscription_process_retries(today)
        self._subscription_process_unpaid(today)

    def _subscription_run_safe(self, method, *args):
        for order in self:
            try:
                with self.env.cr.savepoint():
                    method(order, *args)
            except Exception:  # noqa: BLE001
                _logger.exception('Subscription %s: %s failed', order.name, method.__name__)

    @api.model
    def _subscription_process_end_of_term(self, today):
        orders = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ACTIVE_STATES),
            ('subscription_end_date', '!=', False),
        ])

        def process(order, today):
            plan = order.subscription_plan_id
            if order.subscription_end_date <= today:
                if plan.end_behaviour == 'renew':
                    delta = plan._get_duration_delta() or plan._get_billing_delta()
                    end = order.subscription_end_date
                    while end <= today:
                        end += delta
                    order.subscription_end_date = end
                    order.message_post(body=self.env._('Renewed automatically until %(date)s.',
                                                       date=format_date(self.env, end)))
                else:
                    reason = self.env.ref('om_sale_subscription.close_reason_end_of_term', raise_if_not_found=False)
                    order._subscription_close(reason=reason)
            elif plan.end_behaviour == 'quotation' and \
                    order.subscription_end_date - relativedelta(days=plan.renewal_notice_days) <= today and \
                    not order.subscription_child_ids.filtered(
                        lambda o: o.subscription_type == 'renewal' and o.state != 'cancel'):
                renewal = order._subscription_create_renewal()
                renewal._subscription_send_mail('om_sale_subscription.mail_template_subscription_renewal')
                renewal.filtered(lambda o: o.state == 'draft').action_quotation_sent()

        orders._subscription_run_safe(process, today)

    @api.model
    def _subscription_process_invoices(self, today):
        orders = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ('progress', 'renewed')),
            ('subscription_next_invoice_date', '<=', today),
        ]).filtered(lambda o: o._subscription_is_due(today))

        def process(order, today):  # noqa: ARG001
            invoice = order._subscription_create_invoices()
            if invoice and order.subscription_plan_id.invoice_mode == 'posted':
                # Posting sends the invoice and charges it, see account.move._post().
                invoice.action_post()

        orders._subscription_run_safe(process, today)

    @api.model
    def _subscription_process_retries(self, today):
        orders = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ('progress', 'renewed')),
            ('subscription_payment_retry_date', '<=', today),
            ('subscription_token_id', '!=', False),
        ])

        def process(order, today):  # noqa: ARG001
            invoice = order._subscription_unpaid_invoices()[:1]
            order.subscription_payment_retry_date = False
            if invoice:
                order._subscription_charge_invoice(invoice)

        orders._subscription_run_safe(process, today)

    @api.model
    def _subscription_process_unpaid(self, today):
        orders = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ACTIVE_STATES),
            ('subscription_plan_id.auto_close_days', '>', 0),
        ])
        if not orders:
            return
        invoices = orders._subscription_unpaid_invoices()
        reason = self.env.ref('om_sale_subscription.close_reason_unpaid', raise_if_not_found=False)
        for order in orders:
            oldest = invoices.filtered(lambda inv, order=order: inv.subscription_id == order)[:1]
            due = oldest.invoice_date_due or oldest.invoice_date
            if due and due + relativedelta(days=order.subscription_plan_id.auto_close_days) < today:
                order._subscription_run_safe(lambda o, r: o._subscription_close(reason=r), reason)

    # ------------------------------------------------------------
    # Portal
    # ------------------------------------------------------------

    def _compute_access_url(self):
        super()._compute_access_url()
        for order in self.filtered(lambda o: o.is_subscription and o.state == 'sale'):
            order.access_url = f'/my/subscriptions/{order.id}'

    @api.model
    def _subscription_portal_domain(self, partner):
        return Domain([
            ('partner_id', 'child_of', partner.commercial_partner_id.id),
            ('is_subscription', '=', True),
            ('state', '=', 'sale'),
        ])
