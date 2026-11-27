from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import date_utils

PERIODS = [
    ('month', 'Monthly'),
    ('quarter', 'Quarterly'),
    ('year', 'Yearly'),
]
PERIOD_MONTHS = {'month': 1, 'quarter': 3, 'year': 12}
PAID_STATES = ('paid', 'in_payment', 'reversed')


class OmCommissionPlan(models.Model):
    _name = 'om.commission.plan'
    _description = 'Commission Plan'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    plan_type = fields.Selection([
        ('user', 'Salespersons'),
        ('team', 'Sales Teams'),
        ('partner', 'Resellers'),
    ], string='Commission For', required=True, default='user', tracking=True)
    period = fields.Selection(PERIODS, required=True, default='month', tracking=True,
                              help='Commissions and targets are computed for each period.')
    date_from = fields.Date(string='Valid From', tracking=True)
    date_to = fields.Date(string='Valid Until', tracking=True)
    base = fields.Selection([
        ('invoice', 'Invoices'),
        ('order', 'Confirmed Sales Orders'),
    ], string='Commission Based On', required=True, default='invoice', tracking=True,
        help='Invoices: customer invoices count and credit notes reduce the commission. '
             'Confirmed Sales Orders: the order lines count at the order date; a cancelled order is taken back.')
    invoice_state = fields.Selection([
        ('posted', 'When Posted'),
        ('paid', 'When Paid'),
    ], string='Count Invoices', required=True, default='posted', tracking=True,
        help='When Posted: at the invoice date. When Paid: at the date the invoice is fully paid.')
    commission_type = fields.Selection([
        ('rules', 'Commission Rules'),
        ('target', 'Target and Achievement Tiers'),
    ], string='Compute With', required=True, default='rules', tracking=True,
        help='Commission Rules: a percentage of the revenue or margin, or a fixed amount per unit, per product, '
             'product category or for all products. Target and Achievement Tiers: the rate depends on the share '
             'of the target reached in the period.')
    user_ids = fields.Many2many('res.users', 'om_commission_plan_user_rel', 'plan_id', 'user_id',
                                string='Salespersons', domain=[('share', '=', False)],
                                help='Leave empty for all salespersons.')
    team_ids = fields.Many2many('crm.team', 'om_commission_plan_team_rel', 'plan_id', 'team_id',
                                string='Sales Teams', help='Leave empty for all sales teams.')
    partner_ids = fields.Many2many('res.partner', 'om_commission_plan_partner_rel', 'plan_id', 'partner_id',
                                   string='Resellers')
    grade_ids = fields.Many2many('om.commission.grade', 'om_commission_plan_grade_rel', 'plan_id', 'grade_id',
                                 string='Reseller Grades',
                                 help='Resellers with one of these grades get this plan. Leave resellers and '
                                      'grades empty for every referrer.')
    rule_ids = fields.One2many('om.commission.rule', 'plan_id', string='Rules', copy=True)
    tier_ids = fields.One2many('om.commission.tier', 'plan_id', string='Achievement Tiers', copy=True)
    target_ids = fields.One2many('om.commission.target', 'plan_id', string='Targets', copy=True)
    target_amount = fields.Monetary(string='Target per Period', tracking=True,
                                    help='Target of each salesperson, team or reseller for one period, '
                                         'unless a specific target is set below.')
    target_base = fields.Selection([
        ('revenue', 'Revenue'),
        ('margin', 'Margin'),
    ], string='Target On', required=True, default='revenue')
    cap_amount = fields.Monetary(string='Cap per Period', tracking=True,
                                 help='Maximum commission of one person for one period. Zero means no cap.')
    team_split = fields.Selection([
        ('seller', 'To the Salesperson of the Document'),
        ('equal', 'Equally between Team Members'),
    ], string='Team Commission', required=True, default='seller')
    manager_override = fields.Float(
        string='Team Leader Override (%)', digits=(16, 2),
        help='The team leader also earns this share of every commission of the team.')
    line_count = fields.Integer(compute='_compute_line_count')
    note = fields.Html()

    _date_check = models.Constraint(
        'CHECK(date_from IS NULL OR date_to IS NULL OR date_from <= date_to)',
        'The end of the validity must come after its start.',
    )
    _cap_check = models.Constraint('CHECK(cap_amount >= 0)', 'The cap cannot be negative.')

    def _compute_line_count(self):
        data = dict(self.env['om.commission.line']._read_group(
            [('plan_id', 'in', self.ids)], ['plan_id'], ['__count']))
        for plan in self:
            plan.line_count = data.get(plan, 0)

    @api.constrains('manager_override')
    def _check_manager_override(self):
        for plan in self:
            if not 0 <= plan.manager_override <= 100:
                raise ValidationError(self.env._('The team leader override must be between 0 and 100%.'))

    @api.constrains('commission_type', 'tier_ids')
    def _check_tiers(self):
        for plan in self:
            if plan.commission_type == 'target' and not plan.tier_ids:
                raise ValidationError(self.env._(
                    'Add at least one achievement tier to the plan %(plan)s.', plan=plan.name))

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_recompute(self):
        today = fields.Date.context_today(self)
        for plan in self:
            start = date_utils.start_of(today, plan.period)
            previous = date_utils.start_of(start - timedelta(days=1), plan.period)
            plan._compute_commissions(previous, today)
        return True

    def action_view_lines(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_commission.action_commission_line')
        action['domain'] = [('plan_id', '=', self.id)]
        action['context'] = {'search_default_group_period': 1}
        return action

    @api.model
    def _cron_recompute(self):
        self.search([]).action_recompute()

    # ------------------------------------------------------------
    # Periods
    # ------------------------------------------------------------

    def _get_periods(self, date_from, date_to):
        """Periods of the plan (start, end) that overlap the given dates and the validity of the plan."""
        self.ensure_one()
        periods = []
        start = date_utils.start_of(date_from, self.period)
        while start <= date_to:
            end = date_utils.end_of(start, self.period)
            if (not self.date_to or start <= self.date_to) and (not self.date_from or end >= self.date_from):
                periods.append((start, end))
            start = end + timedelta(days=1)
        return periods

    def _get_period_of(self, day):
        self.ensure_one()
        return date_utils.start_of(day, self.period), date_utils.end_of(day, self.period)

    # ------------------------------------------------------------
    # Sources: one dict per invoice line, order line or other document line
    # ------------------------------------------------------------

    def _get_commission_sources(self, date_from, date_to):
        """Return the documents lines of the period that may earn a commission, as dicts with the keys
        key, date, name, user, team, referrer, customer, product, quantity, revenue, cost, move, order and
        reversed_move. Amounts are in the currency of the company, negative for credit notes."""
        self.ensure_one()
        if self.base == 'order':
            return self._get_order_sources(date_from, date_to)
        return self._get_invoice_sources(date_from, date_to)

    def _get_invoice_scope_domain(self):
        self.ensure_one()
        if self.plan_type == 'user':
            if self.user_ids:
                return Domain('move_id.invoice_user_id', 'in', self.user_ids.ids)
            return Domain('move_id.invoice_user_id', '!=', False)
        if self.plan_type == 'team':
            if self.team_ids:
                return Domain('move_id.team_id', 'in', self.team_ids.ids)
            return Domain('move_id.team_id', '!=', False)
        return Domain('move_id.om_referrer_id', '!=', False)

    def _get_order_scope_domain(self):
        self.ensure_one()
        if self.plan_type == 'user':
            if self.user_ids:
                return Domain('order_id.user_id', 'in', self.user_ids.ids)
            return Domain('order_id.user_id', '!=', False)
        if self.plan_type == 'team':
            if self.team_ids:
                return Domain('order_id.team_id', 'in', self.team_ids.ids)
            return Domain('order_id.team_id', '!=', False)
        return Domain('order_id.om_referrer_id', '!=', False)

    def _get_invoice_sources(self, date_from, date_to):
        self.ensure_one()
        domain = Domain([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('display_type', '=', 'product'),
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
        ]) & self._get_invoice_scope_domain()
        paid_dates = {}
        if self.invoice_state == 'paid':
            partials = self.env['account.partial.reconcile'].search([
                ('company_id', '=', self.company_id.id),
                ('max_date', '>=', date_from),
                ('max_date', '<=', date_to),
            ])
            moves = (partials.debit_move_id | partials.credit_move_id).move_id.filtered(
                lambda m: m.move_type in ('out_invoice', 'out_refund') and m.payment_state in PAID_STATES)
            for move in moves:
                paid_date = move._om_commission_paid_date()
                if paid_date and date_from <= paid_date <= date_to:
                    paid_dates[move.id] = paid_date
            domain &= Domain('move_id', 'in', list(paid_dates))
        else:
            domain &= Domain([('move_id.invoice_date', '>=', date_from), ('move_id.invoice_date', '<=', date_to)])
        sources = []
        for line in self.env['account.move.line'].search(domain, order='date, id'):
            move = line.move_id
            date = paid_dates.get(move.id) or move.invoice_date
            sources.append(self._prepare_invoice_source(line, date))
        return sources

    def _prepare_invoice_source(self, line, date):
        move = line.move_id
        sign = -1 if move.move_type == 'out_refund' else 1
        return {
            'key': f'aml,{line.id}',
            'date': date,
            'name': f'{move.name} - {line.product_id.display_name or line.name or ""}'.strip(' -'),
            'user': move.invoice_user_id,
            'team': move.team_id,
            'referrer': move.om_referrer_id,
            'customer': move.commercial_partner_id,
            'product': line.product_id,
            'quantity': line.quantity * sign,
            'revenue': -line.balance,
            'cost': self._get_invoice_line_cost(line, date) * sign,
            'move': move,
            'order': line.sale_line_ids.order_id[:1],
            'reversed_move': move.reversed_entry_id,
        }

    def _get_invoice_line_cost(self, line, date):
        company = self.company_id
        qty = abs(line.quantity)
        sale_line = line.sale_line_ids[:1]
        if sale_line and 'purchase_price' in sale_line._fields and sale_line.product_uom_id:
            unit = sale_line.currency_id._convert(sale_line.purchase_price, company.currency_id, company, date)
            uom_qty = line.product_uom_id._compute_quantity(qty, sale_line.product_uom_id) \
                if line.product_uom_id else qty
            return unit * uom_qty
        product = line.product_id
        if product:
            uom_qty = line.product_uom_id._compute_quantity(qty, product.uom_id) if line.product_uom_id else qty
            return product.with_company(company).standard_price * uom_qty
        return 0.0

    def _get_order_sources(self, date_from, date_to):
        self.ensure_one()
        company = self.company_id
        domain = Domain([
            ('company_id', '=', company.id),
            ('state', '=', 'sale'),
            ('display_type', '=', False),
            ('is_downpayment', '=', False),
            ('order_id.date_order', '>=', fields.Datetime.to_datetime(date_from)),
            ('order_id.date_order', '<', fields.Datetime.to_datetime(date_to + timedelta(days=1))),
        ]) & self._get_order_scope_domain()
        sources = []
        for line in self.env['sale.order.line'].search(domain, order='id'):
            order = line.order_id
            date = order.date_order.date()
            revenue = order.currency_id._convert(line.price_subtotal, company.currency_id, company, date)
            sources.append({
                'key': f'sol,{line.id}',
                'date': date,
                'name': f'{order.name} - {line.product_id.display_name}',
                'user': order.user_id,
                'team': order.team_id,
                'referrer': order.om_referrer_id,
                'customer': order.partner_id.commercial_partner_id,
                'product': line.product_id,
                'quantity': line.product_uom_qty,
                'revenue': revenue,
                'cost': self._get_order_line_cost(line, date),
                'move': self.env['account.move'],
                'order': order,
                'reversed_move': self.env['account.move'],
            })
        return sources

    def _get_order_line_cost(self, line, date):
        company = self.company_id
        if 'purchase_price' in line._fields:
            unit = line.currency_id._convert(line.purchase_price, company.currency_id, company, date)
            return unit * line.product_uom_qty
        product = line.product_id
        qty = line.product_uom_id._compute_quantity(line.product_uom_qty, product.uom_id) \
            if line.product_uom_id else line.product_uom_qty
        return product.with_company(company).standard_price * qty

    # ------------------------------------------------------------
    # Holders, targets, rules and beneficiaries
    # ------------------------------------------------------------

    def _get_source_holder(self, source):
        """The salesperson, team or reseller whose target and achievement the source counts for."""
        self.ensure_one()
        if self.plan_type == 'user':
            user = source['user']
            if user and (not self.user_ids or user in self.user_ids):
                return user
        elif self.plan_type == 'team':
            team = source['team']
            if team and (not self.team_ids or team in self.team_ids):
                return team
        else:
            referrer = source['referrer']
            if referrer and self._is_plan_reseller(referrer):
                return referrer
        return None

    def _is_plan_reseller(self, partner):
        self.ensure_one()
        if not self.partner_ids and not self.grade_ids:
            return True
        return partner in self.partner_ids or (
            partner.om_commission_grade_id and partner.om_commission_grade_id in self.grade_ids)

    def _get_target(self, holder):
        self.ensure_one()
        field = {'user': 'user_id', 'team': 'team_id', 'partner': 'partner_id'}[self.plan_type]
        target = self.target_ids.filtered(lambda t: t[field] == holder)[:1]
        return target.target_amount if target else self.target_amount

    def _get_tier(self, achievement):
        self.ensure_one()
        for tier in self.tier_ids.sorted('achievement_from', reverse=True):
            if achievement >= tier.achievement_from:
                return tier
        return self.env['om.commission.tier']

    def _get_rule(self, product):
        self.ensure_one()
        rules = self.rule_ids.filtered(lambda r: r._match_product(product))
        return rules.sorted(lambda r: (r._get_priority(), r.sequence, r.id))[:1]

    def _get_beneficiaries(self, holder, source):
        """List of (user, partner, role, share) earning the commission of a source."""
        self.ensure_one()
        if self.plan_type == 'user':
            return [(holder, holder.partner_id, 'seller', 1.0)]
        if self.plan_type == 'partner':
            return [(self.env['res.users'], holder, 'reseller', 1.0)]
        team = holder
        result = []
        if self.team_split == 'equal':
            members = team.member_ids or team.user_id
            for member in members:
                result.append((member, member.partner_id, 'member', 1.0 / len(members)))
        else:
            seller = source['user'] or team.user_id
            if seller:
                result.append((seller, seller.partner_id, 'member', 1.0))
        if self.manager_override and team.user_id:
            result.append((team.user_id, team.user_id.partner_id, 'leader', self.manager_override / 100.0))
        return result

    # ------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------

    def _get_locked_lines(self):
        """Lines of the plan already approved or paid and not taken back."""
        self.ensure_one()
        lines = self.env['om.commission.line'].search([
            ('plan_id', '=', self.id),
            ('state', 'in', ('approved', 'paid')),
            ('is_clawback', '=', False),
        ])
        return lines.filtered(lambda line: not line.clawback_line_ids)

    def _compute_commissions(self, date_from, date_to):
        """Recompute the commission lines and achievements of the periods of the plans between two dates.
        Lines already in an approved or paid statement are kept: they are never computed again, and a
        line is taken back (clawback) when its source document is cancelled or no longer counts."""
        Line = self.env['om.commission.line'].sudo()
        Achievement = self.env['om.commission.achievement'].sudo()
        new_lines = Line
        for plan in self.sudo():
            periods = plan._get_periods(date_from, date_to)
            Line.search([
                ('plan_id', '=', plan.id),
                ('state', 'in', ('open', 'draft')),
                '|',
                ('is_clawback', '=', True),
                '&', ('period_start', '>=', periods[0][0] if periods else date_from),
                ('period_start', '<=', periods[-1][0] if periods else date_to),
            ]).unlink()
            if not periods:
                new_lines |= plan._create_clawback_lines()
                continue
            Achievement.search([
                ('plan_id', '=', plan.id),
                ('period_start', '>=', periods[0][0]),
                ('period_start', '<=', periods[-1][0]),
            ]).unlink()
            locked = plan._get_locked_lines()
            locked_keys = {(line.source_key, line.user_id.id, line.partner_id.id, line.role) for line in locked}
            locked_moves = locked.move_id
            line_vals, achievement_vals = [], []
            for start, end in periods:
                sources = plan._get_commission_sources(
                    max(start, plan.date_from or start), min(end, plan.date_to or end))
                vals, ach_vals = plan._prepare_period_values(sources, start, end, locked, locked_keys, locked_moves)
                line_vals += vals
                achievement_vals += ach_vals
            new_lines |= Line.create(line_vals)
            Achievement.create(achievement_vals)
            new_lines |= plan._create_clawback_lines()
        new_lines._attach_to_draft_statements()
        return new_lines

    def _prepare_period_values(self, sources, start, end, locked, locked_keys, locked_moves):
        self.ensure_one()
        currency = self.currency_id
        groups = defaultdict(list)
        for source in sources:
            holder = self._get_source_holder(source)
            if holder:
                groups[holder].append(source)
        locked_by_move = defaultdict(lambda: self.env['om.commission.line'])
        for line in locked.filtered('move_id'):
            locked_by_move[line.move_id] |= line
        locked_source_keys = set(locked.mapped('source_key'))
        line_vals, achievement_vals = [], []
        for holder, all_sources in groups.items():
            # Credit notes of invoices already approved or paid take back the commission at its original
            # rate, and do not count for the achievement of the period.
            holder_sources, refund_sources = [], []
            for source in all_sources:
                reversed_move = source.get('reversed_move')
                if reversed_move and reversed_move in locked_by_move and source['key'] not in locked_source_keys:
                    refund_sources.append(source)
                else:
                    holder_sources.append(source)
            revenue = sum(s['revenue'] for s in holder_sources)
            margin = sum(s['revenue'] - s['cost'] for s in holder_sources)
            target = self._get_target(holder)
            achieved = revenue if self.target_base == 'revenue' else margin
            achievement = achieved / target * 100.0 if target else 0.0
            tier = self._get_tier(achievement) if self.commission_type == 'target' else None
            holder_vals = []
            for source in holder_sources:
                rule = self.env['om.commission.rule']
                if self.commission_type == 'rules':
                    rule = self._get_rule(source['product'])
                    if not rule:
                        continue
                    amount, rate = rule._compute_commission(source)
                else:
                    rate = tier.rate if tier else 0.0
                    base = source['revenue'] if self.target_base == 'revenue' else source['revenue'] - source['cost']
                    amount = base * rate / 100.0
                if currency.is_zero(amount):
                    continue
                for user, partner, role, share in self._get_beneficiaries(holder, source):
                    if (source['key'], user.id, partner.id, role) in locked_keys:
                        continue
                    holder_vals.append(self._prepare_line_values(
                        source, holder, user, partner, role, rate, amount * share, rule, start, end, locked_moves))
            for source in refund_sources:
                holder_vals += self._prepare_refund_line_values(
                    source, holder, locked_by_move[source['reversed_move']], start, end, locked_keys, locked_moves)
            line_vals += holder_vals
            achievement_vals.append({
                'plan_id': self.id,
                'company_id': self.company_id.id,
                'user_id': holder.id if self.plan_type == 'user' else False,
                'team_id': holder.id if self.plan_type == 'team' else False,
                'partner_id': holder.id if self.plan_type == 'partner' else False,
                'period_start': start,
                'period_end': end,
                'revenue': revenue,
                'margin': margin,
                'target_amount': target,
                'achievement': achievement,
                'rate': tier.rate if tier else 0.0,
                'commission': sum(v['amount'] for v in holder_vals) + sum(
                    locked.filtered(lambda line: line.period_start == start and line._get_holder() == holder)
                    .mapped('amount')),
            })
        self._apply_cap(line_vals, locked.filtered(lambda line: line.period_start == start))
        return line_vals, achievement_vals

    def _prepare_line_values(self, source, holder, user, partner, role, rate, amount, rule, start, end, locked_moves):
        self.ensure_one()
        reversed_move = source.get('reversed_move')
        return {
            'name': source['name'],
            'plan_id': self.id,
            'rule_id': rule.id if rule else False,
            'company_id': self.company_id.id,
            'date': source['date'],
            'period_start': start,
            'period_end': end,
            'user_id': user.id,
            'partner_id': partner.id,
            'team_id': (holder.id if self.plan_type == 'team' else source['team'].id) or False,
            'role': role,
            'customer_id': source['customer'].id,
            'product_id': source['product'].id,
            'quantity': source['quantity'],
            'base_amount': source['revenue'],
            'margin_amount': source['revenue'] - source['cost'],
            'rate': rate,
            'amount': self.currency_id.round(amount),
            'move_id': source['move'].id,
            'order_id': source['order'].id,
            'source_key': source['key'],
            'is_clawback': bool(reversed_move and reversed_move in locked_moves),
        }

    def _prepare_refund_line_values(self, source, holder, original_lines, start, end, locked_keys, locked_moves):
        """Take back the commission of an approved or paid invoice in proportion to its credit note, with the
        rate and for the beneficiaries of the original commission."""
        self.ensure_one()
        lines = original_lines.filtered(lambda line: line.product_id == source['product']) or original_lines
        totals = defaultdict(lambda: [0.0, 0.0, self.env['om.commission.line']])
        for line in lines:
            total = totals[(line.user_id, line.partner_id, line.role)]
            total[0] += line.amount
            total[1] += line.base_amount
            total[2] |= line
        vals_list = []
        for (user, partner, role), (amount, base, group) in totals.items():
            if (source['key'], user.id, partner.id, role) in locked_keys or self.currency_id.is_zero(base):
                continue
            commission = source['revenue'] * amount / base
            if self.currency_id.is_zero(commission):
                continue
            vals = self._prepare_line_values(source, holder, user, partner, role, group[:1].rate, commission,
                                             group[:1].rule_id, start, end, locked_moves)
            vals['is_clawback'] = True
            vals_list.append(vals)
        return vals_list

    def _apply_cap(self, line_vals, locked_lines):
        """Scale the new lines of each person down so that the commission of the period stays under the cap."""
        self.ensure_one()
        if not self.cap_amount:
            return
        totals = defaultdict(float)
        line_vals = [vals for vals in line_vals if not vals.get('is_clawback')]
        for vals in line_vals:
            totals[(vals['user_id'], vals['partner_id'])] += vals['amount']
        for (user_id, partner_id), total in totals.items():
            done = sum(locked_lines.filtered(
                lambda line: line.user_id.id == user_id and line.partner_id.id == partner_id).mapped('amount'))
            if total <= 0 or done + total <= self.cap_amount:
                continue
            factor = max(self.cap_amount - done, 0.0) / total
            for vals in line_vals:
                if vals['user_id'] == user_id and vals['partner_id'] == partner_id:
                    vals['amount'] = self.currency_id.round(vals['amount'] * factor)
                    vals['capped'] = True

    def _create_clawback_lines(self):
        """Take back approved or paid commissions whose source document no longer counts."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        start, end = self._get_period_of(today)
        vals_list = []
        for line in self._get_locked_lines():
            if line._is_source_valid():
                continue
            vals_list.append({
                'name': self.env._('Clawback: %(line)s', line=line.name),
                'plan_id': self.id,
                'rule_id': line.rule_id.id,
                'company_id': line.company_id.id,
                'date': today,
                'period_start': start,
                'period_end': end,
                'user_id': line.user_id.id,
                'partner_id': line.partner_id.id,
                'team_id': line.team_id.id,
                'role': line.role,
                'customer_id': line.customer_id.id,
                'product_id': line.product_id.id,
                'quantity': -line.quantity,
                'base_amount': -line.base_amount,
                'margin_amount': -line.margin_amount,
                'rate': line.rate,
                'amount': -line.amount,
                'move_id': line.move_id.id,
                'order_id': line.order_id.id,
                'source_key': f'{line.source_key}:clawback',
                'is_clawback': True,
                'origin_line_id': line.id,
            })
        return self.env['om.commission.line'].sudo().create(vals_list)


class OmCommissionRule(models.Model):
    _name = 'om.commission.rule'
    _description = 'Commission Rule'
    _order = 'plan_id, sequence, id'

    plan_id = fields.Many2one('om.commission.plan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one(related='plan_id.currency_id')
    applies_on = fields.Selection([
        ('all', 'All Products'),
        ('category', 'Product Category'),
        ('product', 'Product'),
    ], required=True, default='all',
        help='A rule on a product comes before a rule on its category, which comes before a rule on all products.')
    categ_id = fields.Many2one('product.category', string='Category')
    product_tmpl_id = fields.Many2one('product.template', string='Product')
    compute_type = fields.Selection([
        ('revenue', 'Percentage of Revenue'),
        ('margin', 'Percentage of Margin'),
        ('fixed', 'Fixed Amount per Unit'),
    ], string='Commission', required=True, default='revenue')
    rate = fields.Float(string='Rate (%)', digits=(16, 2))
    fixed_amount = fields.Monetary(string='Amount per Unit')

    @api.constrains('applies_on', 'categ_id', 'product_tmpl_id')
    def _check_target(self):
        for rule in self:
            if rule.applies_on == 'category' and not rule.categ_id:
                raise ValidationError(self.env._('Set the product category of the rule.'))
            if rule.applies_on == 'product' and not rule.product_tmpl_id:
                raise ValidationError(self.env._('Set the product of the rule.'))

    @api.depends('applies_on', 'categ_id', 'product_tmpl_id', 'compute_type', 'rate', 'fixed_amount')
    def _compute_display_name(self):
        types = dict(self._fields['compute_type']._description_selection(self.env))
        for rule in self:
            if rule.applies_on == 'product':
                target = rule.product_tmpl_id.display_name
            elif rule.applies_on == 'category':
                target = rule.categ_id.display_name
            else:
                target = self.env._('All Products')
            value = rule.fixed_amount if rule.compute_type == 'fixed' else f'{rule.rate:g}%'
            rule.display_name = f'{target}: {types.get(rule.compute_type)} {value}'

    def _match_product(self, product):
        self.ensure_one()
        if self.applies_on == 'all':
            return True
        if not product:
            return False
        if self.applies_on == 'product':
            return product.product_tmpl_id == self.product_tmpl_id
        categ = product.categ_id
        return bool(categ) and self.categ_id.parent_path and categ.parent_path.startswith(self.categ_id.parent_path)

    def _get_priority(self):
        self.ensure_one()
        return {'product': 0, 'category': 1, 'all': 2}[self.applies_on]

    def _compute_commission(self, source):
        """Commission amount and rate of the rule for a source."""
        self.ensure_one()
        if self.compute_type == 'fixed':
            return self.fixed_amount * source['quantity'], 0.0
        base = source['revenue'] if self.compute_type == 'revenue' else source['revenue'] - source['cost']
        return base * self.rate / 100.0, self.rate


class OmCommissionTier(models.Model):
    _name = 'om.commission.tier'
    _description = 'Commission Achievement Tier'
    _order = 'plan_id, achievement_from, id'

    plan_id = fields.Many2one('om.commission.plan', required=True, ondelete='cascade', index=True)
    achievement_from = fields.Float(string='From Achievement (%)', digits=(16, 2), required=True,
                                    help='The tier applies when the share of the target reached in the period '
                                         'is at least this percentage, up to the next tier.')
    rate = fields.Float(string='Commission Rate (%)', digits=(16, 2),
                        help='Percentage of the revenue or margin of the period paid as commission.')

    _plan_achievement_uniq = models.Constraint(
        'UNIQUE(plan_id, achievement_from)', 'Two tiers of a plan cannot start at the same achievement.')


class OmCommissionTarget(models.Model):
    _name = 'om.commission.target'
    _description = 'Commission Target'
    _order = 'plan_id, id'

    plan_id = fields.Many2one('om.commission.plan', required=True, ondelete='cascade', index=True)
    plan_type = fields.Selection(related='plan_id.plan_type')
    currency_id = fields.Many2one(related='plan_id.currency_id')
    user_id = fields.Many2one('res.users', string='Salesperson', domain=[('share', '=', False)])
    team_id = fields.Many2one('crm.team', string='Sales Team')
    partner_id = fields.Many2one('res.partner', string='Reseller')
    target_amount = fields.Monetary(string='Target per Period', required=True)
