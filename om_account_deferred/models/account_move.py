from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_deferred_origin_id = fields.Many2one(
        'account.move', string='Deferral Of', readonly=True, index='btree_not_null',
        ondelete='cascade', copy=False,
        help="The invoice or bill whose deferral this entry is part of.")
    om_deferral_ids = fields.One2many(
        'account.move', 'om_deferred_origin_id', string='Deferral Entries',
        readonly=True)
    om_deferral_count = fields.Integer(compute='_compute_om_deferral_count')
    om_has_deferrals = fields.Boolean(
        compute='_compute_om_has_deferrals',
        help="Technical: whether any line on this document asks to be deferred.")
    om_deferred_generation = fields.Selection(
        [('on_post', 'On validation'), ('manual', 'Manually & Grouped')], compute='_compute_om_deferred_generation',
        help="Technical: how the deferral entries of this document are generated, from the settings of its side.")
    # the grouped entries of Manually & Grouped: the period they adjust and the side of profit and loss
    om_deferred_period_end = fields.Date(string='Deferral Period End', readonly=True, copy=False, index=True)
    om_deferred_kind = fields.Selection(
        [('expense', 'Deferred Expense'), ('revenue', 'Deferred Revenue')],
        string='Deferral Kind', readonly=True, copy=False)

    @api.depends('move_type', 'company_id')
    def _compute_om_deferred_generation(self):
        for move in self:
            kind = 'expense' if move.is_purchase_document(include_receipts=True) else 'revenue'
            move.om_deferred_generation = move.company_id.om_deferred_expense_generation if kind == 'expense' \
                else move.company_id.om_deferred_revenue_generation

    @api.depends('om_deferral_ids')
    def _compute_om_deferral_count(self):
        for move in self:
            move.om_deferral_count = len(move.om_deferral_ids)

    @api.depends('line_ids.om_deferred_start_date', 'line_ids.om_deferred_end_date')
    def _compute_om_has_deferrals(self):
        for move in self:
            move.om_has_deferrals = any(
                line._om_needs_deferral() for line in move.line_ids)

    # ------------------------------------------------------------------
    # Generating
    # ------------------------------------------------------------------
    def _om_deferral_settings(self, kind):
        """ The journal and the account of one side, refusing to go on without them. """
        settings = (self.company_id or self.env.company)._om_deferred_settings(kind)
        names = {'expense': _("deferred expense"), 'revenue': _("deferred revenue")}
        if not settings['account_id']:
            raise UserError(_(
                "Set the %(side)s account in the accounting settings before deferring anything.", side=names[kind]))
        if not settings['journal_id']:
            raise UserError(_(
                "Set the %(side)s journal in the accounting settings before deferring anything.", side=names[kind]))
        return settings

    @api.model
    def _om_deferral_line_pair(self, label, account, deferred_account, amount, partner=None, product=None,
                               analytic=None):
        """ The two lines moving ``amount`` between a profit and loss account and its deferral account.

        The sign does the work: a cost is a positive balance and income a negative one, so the same
        two lines serve both directions without asking which is which. """
        common = {
            'name': label,
            'partner_id': partner.id if partner else False,
            'product_id': product.id if product else False,
            'analytic_distribution': analytic or False,
        }
        return [
            Command.create(dict(common, account_id=account.id, balance=amount)),
            Command.create(dict(common, account_id=deferred_account.id, balance=-amount)),
        ]

    @api.model
    def _om_post_or_schedule(self, moves):
        """ Post the entries whose date has come, let the others post themselves on their date. """
        today = fields.Date.context_today(self)
        due = moves.filtered(lambda move: move.date <= today)
        due.action_post()
        (moves - due).auto_post = 'at_date'
        return moves

    def _om_generate_deferrals(self, kinds=('expense', 'revenue')):
        """ Park the amount of each deferred line of the sides ``kinds``, then release it period by
        period: one entry per date and journal for the whole document. """
        created = self.env['account.move']
        for move in self:
            if move.state != 'posted' or move.om_deferred_origin_id:
                continue
            lines = move.line_ids.filtered(lambda line: line._om_deferral_kind() in kinds and line._om_needs_deferral())
            if not lines:
                continue
            label = _("Deferral of %(document)s", document=move.name or '')
            by_key = defaultdict(list)
            for line in lines:
                settings = move._om_deferral_settings(line._om_deferral_kind())
                pair = (line.account_id, settings['account_id'], line.partner_id, line.product_id,
                        line.analytic_distribution)
                journal = settings['journal_id']
                # Out of profit and loss, in full, on the document's own date.
                by_key[(move.date, journal)].append(pair + (-line.balance,))
                # Back in, a period at a time.
                for date, amount in line._om_deferral_schedule():
                    by_key[(date, journal)].append(pair + (amount,))
            values = []
            for date, journal in sorted(by_key, key=lambda key: (key[0], key[1].id)):
                line_commands = []
                for account, deferred_account, partner, product, analytic, amount in by_key[(date, journal)]:
                    line_commands += self._om_deferral_line_pair(
                        label, account, deferred_account, amount, partner, product, analytic)
                values.append({
                    'move_type': 'entry',
                    'journal_id': journal.id,
                    'company_id': move.company_id.id,
                    'partner_id': move.partner_id.commercial_partner_id.id,
                    'date': date,
                    'ref': label,
                    'om_deferred_origin_id': move.id,
                    'line_ids': line_commands,
                })
            if values:
                created |= self._om_post_or_schedule(self.env['account.move'].create(values))
        return created

    def action_om_generate_deferrals(self):
        self.ensure_one()
        if self.om_deferral_ids:
            raise UserError(_(
                "This document already has deferral entries. Reset it to draft "
                "to start again."))
        created = self._om_generate_deferrals()
        if not created:
            raise UserError(_(
                "No line on this document asks to be deferred over more than "
                "one period."))
        return True

    def action_om_open_deferrals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Deferral Entries"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('om_deferred_origin_id', '=', self.id)],
            'context': {'create': False},
        }

    # ------------------------------------------------------------------
    # Manually & Grouped
    # ------------------------------------------------------------------
    @api.model
    def _om_grouped_deferral(self, kind, period_end):
        """ One entry, at the end of the period, moving out of profit and loss what the deferred
        lines of ``kind`` recognise after it, and its reversal on the first day of the next period.
        Documents deferred on their own validation are left out. """
        company = self.env.company
        existing = self.search([
            ('company_id', '=', company.id), ('om_deferred_kind', '=', kind),
            ('om_deferred_period_end', '=', period_end), ('state', '!=', 'cancel'),
            ('reversed_entry_id', '=', False)])
        if existing:
            raise UserError(_(
                "The deferral entries of this period are already generated (%(entry)s). Reset that entry "
                "to draft and delete it to generate them again.", entry=existing[0].display_name))
        totals = defaultdict(float)
        for line in self.env['account.move.line']._om_deferred_lines(kind):
            later = sum(amount for date, amount in line._om_deferral_schedule() if date > period_end)
            if not line.company_id.currency_id.is_zero(later):
                key = (line.account_id, frozenset((line.analytic_distribution or {}).items()))
                totals[key] += later
        if not totals:
            raise UserError(_("Nothing is deferred after %(date)s.", date=period_end))
        settings = self._om_deferral_settings(kind)
        deferred_account = settings['account_id']
        label = _("Grouped deferral of %(date)s", date=period_end)
        line_commands = []
        for (account, analytic), amount in totals.items():
            line_commands += self._om_deferral_line_pair(
                label, account, deferred_account, -amount, analytic=dict(analytic) or None)
        move = self.create({
            'move_type': 'entry',
            'journal_id': settings['journal_id'].id,
            'company_id': company.id,
            'date': period_end,
            'ref': label,
            'om_deferred_kind': kind,
            'om_deferred_period_end': period_end,
            'line_ids': line_commands,
        })
        move.action_post()
        reversal = move._reverse_moves([{
            'date': fields.Date.add(period_end, days=1),
            'ref': _("Reversal of %(label)s", label=label),
        }])
        self._om_post_or_schedule(reversal)
        return move | reversal

    # ------------------------------------------------------------------
    # Keeping them in step with the document
    # ------------------------------------------------------------------
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda move: not move.om_deferred_origin_id and not move.om_deferred_kind
                                    and not move.om_deferral_ids):
            kinds = tuple(kind for kind in ('expense', 'revenue')
                          if move.company_id._om_deferred_settings(kind)['generation'] == 'on_post')
            if kinds:
                move._om_generate_deferrals(kinds)
        return posted

    def button_draft(self):
        # A deferral only makes sense against a posted document: left behind, it
        # would go on recognising something that is no longer there.
        for move in self:
            deferrals = move.om_deferral_ids
            if not deferrals:
                continue
            posted = deferrals.filtered(lambda deferral: deferral.state == 'posted')
            if posted:
                # Already in the books. Reverse rather than delete, so a period
                # that has been closed keeps its history.
                posted._reverse_moves(cancel=True)
            (deferrals - posted).unlink()
        return super().button_draft()
