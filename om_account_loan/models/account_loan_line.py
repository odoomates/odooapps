import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import groupby
from odoo.tools.misc import format_date

from .loan_context import LOAN_REVERSE, SCHEDULE_UPDATE, internal, internal_context


# fields set by the schedule, which a paid line keeps
SCHEDULE_FIELDS = {'date', 'opening_balance', 'principal', 'interest', 'rate', 'sequence', 'withholding'}

_logger = logging.getLogger(__name__)


class AccountLoanLine(models.Model):
    _name = 'account.loan.line'
    _description = 'Loan Schedule Line'
    _order = 'loan_id, sequence, id'
    _check_company_auto = True

    loan_id = fields.Many2one('account.loan', string='Loan', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    partner_id = fields.Many2one(related='loan_id.partner_id', string='Lender')
    loan_type = fields.Selection(related='loan_id.loan_type', string='Type', store=True)
    sequence = fields.Integer(string='#', required=True, default=1)
    date = fields.Date(string='Due Date', required=True)
    opening_balance = fields.Monetary(
        string='Opening Balance', help="The principal owed on the due date, before the instalment.")
    principal = fields.Monetary(string='Principal')
    interest = fields.Monetary(string='Interest')
    amount = fields.Monetary(string='Instalment', compute='_compute_amounts', store=True)
    withholding = fields.Monetary(
        string='Withholding Tax', compute='_compute_withholding', store=True, readonly=False,
        help="The tax withheld on the interest, deducted from what is paid to the lender.")
    net_amount = fields.Monetary(
        string='Net Payment', compute='_compute_amounts', store=True,
        help="The instalment less the tax withheld: what the lender receives, taxes on a lease bill excluded.")
    closing_balance = fields.Monetary(string='Closing Balance', compute='_compute_amounts', store=True)
    rate = fields.Float(string='Rate (%)', digits=(16, 4), help="The annual rate of the period.")
    state = fields.Selection(
        [('draft', 'To Pay'), ('posted', 'Paid')], string='Status', required=True, default='draft', copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False, check_company=True)
    payment_date = fields.Date(string='Paid On', readonly=True, copy=False)
    loan_state = fields.Selection(related='loan_id.state', string='Loan Status')
    is_last_paid = fields.Boolean(compute='_compute_is_last_paid')
    is_next = fields.Boolean(
        string='To Post Next', compute='_compute_is_next',
        help="The next instalment to pay (or lease payment to bill) of a running loan: the schedule is paid in order.")
    bill_status = fields.Selection(
        [('to_bill', 'To Bill'), ('draft', 'Draft Bill'), ('posted', 'Billed'), ('paid', 'Paid')],
        string='Bill', compute='_compute_bill_status', help="Where the bill of a lease payment stands.")

    @api.depends('principal', 'interest', 'opening_balance', 'withholding')
    def _compute_amounts(self):
        for line in self:
            line.amount = line.principal + line.interest
            line.net_amount = line.amount - line.withholding
            line.closing_balance = line.opening_balance - line.principal

    @api.depends('interest', 'loan_id.withholding_tax_id')
    def _compute_withholding(self):
        for line in self:
            if line.state == 'posted' or not line.loan_id:
                # a paid line keeps what was withheld
                line.withholding = line.withholding
            else:
                line.withholding = line.loan_id._withholding_amount(line.interest)

    @api.depends('loan_type', 'state', 'move_id.state', 'move_id.payment_state')
    def _compute_bill_status(self):
        for line in self:
            move = line.move_id
            if line.loan_type != 'lease':
                line.bill_status = False
            elif line.state != 'posted' or not move:
                line.bill_status = 'to_bill'
            elif move.state == 'draft':
                line.bill_status = 'draft'
            elif move.payment_state in ('paid', 'in_payment'):
                line.bill_status = 'paid'
            else:
                line.bill_status = 'posted'

    @api.depends('state', 'loan_id.line_ids.state')
    def _compute_is_last_paid(self):
        for line in self:
            paid = line.loan_id.line_ids.filtered(lambda other: other.state == 'posted')
            line.is_last_paid = line.state == 'posted' and line == paid.sorted('sequence')[-1:]

    @api.depends('state', 'loan_id.state', 'loan_id.line_ids.state', 'loan_id.outstanding_amount')
    def _compute_is_next(self):
        for line in self:
            loan = line.loan_id
            line.is_next = (
                line.state == 'draft' and loan.state == 'running' and line == loan.next_line_id
                # a loan pays nothing before it is drawn down
                and (loan.loan_type == 'lease' or loan.currency_id.compare_amounts(loan.outstanding_amount, 0.0) > 0)
            )

    def write(self, vals):
        changes = []
        if not internal(self.env, SCHEDULE_UPDATE):
            if SCHEDULE_FIELDS & set(vals) and self.filtered(lambda line: line.state == 'posted'):
                raise UserError(self.env._('A paid instalment cannot be changed.'))
            if {'state', 'move_id', 'payment_date', 'loan_id'} & set(vals):
                raise UserError(self.env._('Pay an instalment with its Pay button.'))
            changes = [(line, line._describe_change(vals)) for line in self]
        res = super().write(vals)
        for line, description in changes:
            if description:
                line.loan_id.message_post(body=self.env._(
                    'Instalment %(number)s changed: %(changes)s.', number=line.sequence, changes=description))
        if not internal(self.env, SCHEDULE_UPDATE) and {'principal', 'date'} & set(vals):
            self.loan_id._chain_balances()
        return res

    def _describe_change(self, vals):
        """ The changes `vals` makes to the due date or the amounts of the line, as a text for the chatter. """
        self.ensure_one()
        currency = self.currency_id
        parts = []
        if 'date' in vals and fields.Date.to_date(vals['date']) != self.date:
            parts.append(self.env._('due date %(old)s to %(new)s', old=format_date(self.env, self.date),
                                    new=format_date(self.env, fields.Date.to_date(vals['date']))))
        for fname in ('principal', 'interest'):
            if fname in vals and currency.compare_amounts(vals[fname] or 0.0, self[fname]):
                parts.append(self.env._(
                    '%(field)s %(old)s to %(new)s', field=self._fields[fname].get_description(self.env)['string'],
                    old=currency.format(self[fname]), new=currency.format(vals[fname] or 0.0)))
        return ', '.join(parts)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_paid(self):
        if not internal(self.env, SCHEDULE_UPDATE) and self.filtered(lambda line: line.state == 'posted'):
            raise UserError(self.env._('A paid instalment cannot be deleted.'))

    def action_pay(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pay Instalment'),
            'res_model': 'account.loan.pay',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_id': self.id},
        }

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    def action_create_bill(self):
        """ Create the bill of the lease payment and open it. """
        self.ensure_one()
        bill = self._create_bill()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': bill.id,
        }

    def action_create_bills(self):
        """ Create the bills of the lease payments selected, in the order of their schedule. """
        lines = self.filtered(lambda line: line.loan_type == 'lease' and line.state == 'draft')
        if not lines:
            raise UserError(self.env._('Select lease payments to bill.'))
        bills = self.env['account.move']
        for line in lines.sorted(lambda line: (line.loan_id.id, line.sequence)):
            bills |= line._create_bill()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Lease Bills'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
            'context': {'create': False},
        }

    @api.model
    def _cron_create_lease_bills(self):
        """ Bill the lease payments due, of the running leases billed on their due dates. """
        today = fields.Date.context_today(self)
        lines = self.search([
            ('loan_type', '=', 'lease'),
            ('state', '=', 'draft'),
            ('date', '<=', today),
            ('loan_id.state', '=', 'running'),
            ('loan_id.bill_auto_create', '=', True),
        ], order='loan_id, sequence')
        for loan, loan_lines in groupby(lines, key=lambda line: line.loan_id):
            try:
                with self.env.cr.savepoint():
                    for line in loan_lines:
                        line.with_company(loan.company_id)._create_bill()
            except UserError as error:
                _logger.warning('The lease %s could not be billed: %s', loan.display_name, error)
                loan.message_post(body=self.env._('The lease payments due could not be billed: %s', error))

    def _check_to_post(self):
        """ Refuse to pay or bill the line out of the order of the schedule. """
        self.ensure_one()
        loan = self.loan_id
        if self.state == 'posted':
            raise UserError(self.env._('The instalment %s is already paid.', self.sequence))
        if loan.state != 'running':
            raise UserError(self.env._('The loan %s is not running.', loan.display_name))
        earlier = loan.line_ids.filtered(lambda line: line.state == 'draft' and line.sequence < self.sequence)
        if earlier:
            raise UserError(self.env._('Pay the instalments in their order: %s first.', earlier[0].sequence))
        if loan.loan_type != 'lease' and loan.currency_id.compare_amounts(loan.outstanding_amount, 0.0) <= 0:
            raise UserError(self.env._('Nothing is drawn on the loan %s: draw it down first.', loan.display_name))
        if self.currency_id.compare_amounts(self.principal, loan.outstanding_amount) > 0:
            raise UserError(self.env._(
                'The principal of the instalment exceeds the outstanding principal of the loan %s.',
                loan.display_name))

    def _check_payment_date(self, day):
        """ Refuse a payment dated before the start of the loan, or before the payment of the instalment
        before it: the balances of the loan at a date follow the payment dates. """
        self.ensure_one()
        loan = self.loan_id
        if day < loan.date_start:
            raise UserError(self.env._(
                'The payment cannot be dated before the start of the loan %(loan)s, %(date)s.',
                loan=loan.display_name, date=format_date(self.env, loan.date_start)))
        paid = loan.line_ids.filtered(lambda line: line.state == 'posted' and line.payment_date)
        last = max(paid.mapped('payment_date'), default=None)
        if last and day < last:
            raise UserError(self.env._(
                'The instalment before it was paid on %(date)s: date this payment on or after it.',
                date=format_date(self.env, last)))

    def _post_payment(self, day, journal, withholding=None):
        """ Post the payment of the instalment on `day` from `journal`: Dr loan (principal) + Dr interest / Cr
        withholding tax (the tax withheld on the interest) + Cr bank (outstanding payments). An instalment of
        zero is marked paid without entry.

        :param withholding: the tax withheld, the one of the line by default
        """
        self.ensure_one()
        loan = self.loan_id
        if loan.loan_type == 'lease':
            raise UserError(self.env._('A lease payment is paid with the bill of the lessor: create its bill.'))
        self._check_to_post()
        self._check_payment_date(day)
        currency = self.currency_id
        withholding = self.withholding if withholding is None else withholding
        if not loan.withholding_tax_id:
            # nothing is withheld without a withholding tax: no tax line would book it
            withholding = 0.0
        move = self.env['account.move']
        if not currency.is_zero(self.amount):
            label = self.env._('%(loan)s - Instalment %(number)s', loan=loan.name, number=self.sequence)
            lines = loan._principal_lines(self.principal, day, label)
            lines.append((loan.account_interest_id, self.interest,
                          self.env._('%(loan)s - Interest %(number)s', loan=loan.name, number=self.sequence),
                          loan._interest_line_values() if withholding else {}))
            lines += loan._withholding_lines(
                self.interest, withholding, day,
                self.env._('%(loan)s - Withholding tax %(number)s', loan=loan.name, number=self.sequence))
            lines.append((loan._bank_account(journal, 'outbound'), 0.0, label))
            move = loan._create_move(journal, day, lines, 'payment', label)
        self.with_context(**internal_context(SCHEDULE_UPDATE)).write({
            'state': 'posted', 'move_id': move.id, 'payment_date': day, 'withholding': withholding})
        if currency.is_zero(withholding):
            loan.message_post(body=self.env._(
                'Instalment %(number)s paid on %(date)s: %(amount)s (principal %(principal)s, interest '
                '%(interest)s).', number=self.sequence, date=format_date(self.env, day),
                amount=currency.format(self.amount), principal=currency.format(self.principal),
                interest=currency.format(self.interest)))
        else:
            loan.message_post(body=self.env._(
                'Instalment %(number)s paid on %(date)s: %(amount)s (principal %(principal)s, interest '
                '%(interest)s), %(withheld)s withheld.', number=self.sequence, date=format_date(self.env, day),
                amount=currency.format(self.amount), principal=currency.format(self.principal),
                interest=currency.format(self.interest), withheld=currency.format(withholding)))
        loan._update_state()
        return move

    def _prepare_bill_values(self, day):
        """ The values of the bill of the lease payment: a line per liability account repaid (taxes of the
        bills) and the interest line (taxes of the bills and withholding tax). """
        self.ensure_one()
        loan = self.loan_id
        currency = self.currency_id
        label = self.env._('%(lease)s - Lease payment %(number)s', lease=loan.name, number=self.sequence)
        invoice_lines = [
            Command.create({
                'name': self.env._('%(label)s: principal', label=label),
                'account_id': account.id,
                'quantity': 1.0,
                'price_unit': amount,
                'tax_ids': [Command.set(loan.bill_tax_ids.ids)],
            })
            for account, amount, _label in loan._principal_lines(self.principal, day, label)
            if not currency.is_zero(amount)
        ]
        if not currency.is_zero(self.interest):
            invoice_lines.append(Command.create({
                'name': self.env._('%(label)s: interest', label=label),
                'account_id': loan.account_interest_id.id,
                'quantity': 1.0,
                'price_unit': self.interest,
                'tax_ids': [Command.set((loan.bill_tax_ids | loan.withholding_tax_id).ids)],
            }))
        return {
            'move_type': 'in_invoice',
            'partner_id': loan.partner_id.id,
            'journal_id': loan.bill_journal_id.id,
            'invoice_date': day,
            'date': day,
            'currency_id': currency.id,
            'ref': label,
            'loan_id': loan.id,
            'loan_entry_type': 'bill',
            'invoice_line_ids': invoice_lines,
        }

    def _check_bill(self, bill):
        """ Refuse to post the bill of the lease payment when it no longer matches it: the lessor, the currency
        or the amount before taxes changed on the bill. The taxes may change. """
        self.ensure_one()
        loan = self.loan_id
        currency = self.currency_id
        untaxed = sum(bill.invoice_line_ids.mapped('price_subtotal'))
        if bill.commercial_partner_id != loan.partner_id.commercial_partner_id or bill.currency_id != currency \
                or currency.compare_amounts(untaxed, self.amount):
            raise UserError(self.env._(
                'The bill %(bill)s no longer matches the lease payment %(number)s of %(lease)s: %(amount)s before '
                'taxes, billed by %(lessor)s. Correct the bill, or cancel it on the lease and bill the payment again.',
                bill=bill.display_name, number=self.sequence, lease=loan.display_name,
                amount=currency.format(self.amount), lessor=loan.partner_id.display_name))

    def _create_bill(self, day=None):
        """ Create the vendor bill of the lessor for the lease payment, dated `day` (its due date by default),
        posted or left in draft as the lease says. The line is then paid with its bill.

        :return: the bill, or an empty recordset for a payment of zero
        """
        self.ensure_one()
        loan = self.loan_id
        if loan.loan_type != 'lease':
            raise UserError(self.env._('The instalments of a loan are paid from the bank: pay them.'))
        self._check_to_post()
        day = day or self.date
        self._check_payment_date(day)
        loan._check_lock_dates(day, loan.bill_journal_id, has_tax=bool(loan.bill_tax_ids or loan.withholding_tax_id))
        bill = self.env['account.move']
        if not self.currency_id.is_zero(self.amount):
            bill = self.env['account.move'].create(self._prepare_bill_values(day))
        self.with_context(**internal_context(SCHEDULE_UPDATE)).write(
            {'state': 'posted', 'move_id': bill.id, 'payment_date': day})
        if bill and loan.bill_posting == 'posted':
            if bill._loan_needs_document_number():
                loan.message_post(body=self.env._(
                    'The bill %(bill)s is left in draft: its journal asks for the document number of the lessor. '
                    'Enter it and post the bill.', bill=bill.display_name))
            else:
                bill.action_post()
        if bill:
            loan.message_post(body=self.env._(
                'Bill %(bill)s of the lease payment %(number)s created: %(amount)s before taxes.',
                bill=bill.display_name, number=self.sequence, amount=self.currency_id.format(self.amount)))
        loan._update_state()
        return bill

    def action_cancel_payment(self):
        """ Reverse the payment of the last paid instalment: the line is to pay again. """
        for line in self:
            if not line.is_last_paid:
                raise UserError(self.env._('Only the last paid instalment can be cancelled.'))
            loan = line.loan_id
            later = loan.operation_ids.filtered(lambda op: op.state == 'posted' and op.date > line.date)
            if later:
                raise UserError(self.env._('Cancel the operations dated after the instalment first.'))
            move = line.move_id.with_context(**internal_context(LOAN_REVERSE))
            if move.state == 'draft':
                move.button_cancel()
            elif move.state == 'posted':
                if move.is_invoice() and move.payment_state not in ('not_paid', 'reversed'):
                    raise UserError(self.env._(
                        'The bill %s is paid: remove its payment first.', move.display_name))
                loan._check_lock_dates(move.date, move.journal_id, has_tax=bool(move.line_ids.tax_line_id))
                values = {'date': move.date}
                if move.is_invoice():
                    values['invoice_date'] = move.invoice_date or move.date
                move._reverse_moves([values], cancel=True)
            line.with_context(**internal_context(SCHEDULE_UPDATE)).write(
                {'state': 'draft', 'move_id': False, 'payment_date': False})
            line._compute_withholding()
            if loan.loan_type == 'lease':
                loan.message_post(body=self.env._('Bill of the lease payment %s cancelled.', line.sequence))
            else:
                loan.message_post(body=self.env._('Payment of the instalment %s cancelled.', line.sequence))
            if loan.state == 'closed':
                loan.state = 'running'
