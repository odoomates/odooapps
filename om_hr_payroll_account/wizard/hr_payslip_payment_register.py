from collections import defaultdict

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipPaymentRegister(models.TransientModel):
    """ Pay the net salary of confirmed payslips: one payment per employee, matched with the net salary of the
    payslips when the payment has a journal entry. """
    _name = 'hr.payslip.payment.register'
    _description = 'Pay Salaries'
    _check_company_auto = True

    payslip_ids = fields.Many2many('hr.payslip', string='Payslips', required=True, readonly=True)
    company_id = fields.Many2one('res.company', compute='_compute_company_id', store=True, precompute=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True,
        compute='_compute_journal_id', store=True, readonly=False, precompute=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line', compute='_compute_available_payment_method_line_ids')
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string='Payment Method', required=True,
        compute='_compute_payment_method_line_id', store=True, readonly=False, precompute=True,
        domain="[('id', 'in', available_payment_method_line_ids)]",
    )
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    memo = fields.Char(compute='_compute_memo', store=True, readonly=False,
                       help="Left empty, the reference of the payslips is used.")
    employee_count = fields.Integer(compute='_compute_amounts')
    total_amount = fields.Monetary('Amount to Pay', compute='_compute_amounts', currency_field='currency_id')
    can_edit_amount = fields.Boolean(compute='_compute_amounts')
    amount = fields.Monetary(compute='_compute_amount', store=True, readonly=False, currency_field='currency_id')

    @api.depends('payslip_ids')
    def _compute_company_id(self):
        for wizard in self:
            companies = wizard.payslip_ids.company_id
            if len(companies) > 1:
                raise UserError(_('The payslips of several companies cannot be paid together.'))
            wizard.company_id = companies

    @api.depends('company_id')
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(wizard.company_id),
                ('type', 'in', ('bank', 'cash')),
            ], order='type, sequence, id', limit=1)

    @api.depends('journal_id')
    def _compute_available_payment_method_line_ids(self):
        for wizard in self:
            wizard.available_payment_method_line_ids = wizard.journal_id._get_available_payment_method_lines(
                'outbound') if wizard.journal_id else False

    @api.depends('available_payment_method_line_ids')
    def _compute_payment_method_line_id(self):
        for wizard in self:
            if wizard.payment_method_line_id not in wizard.available_payment_method_line_ids._origin:
                wizard.payment_method_line_id = wizard.available_payment_method_line_ids._origin[:1]

    @api.depends('payslip_ids')
    def _compute_memo(self):
        for wizard in self:
            wizard.memo = (wizard.payslip_ids.number or wizard.payslip_ids.name) if len(wizard.payslip_ids) == 1 else False

    def _get_payment_groups(self):
        """ :return: {(partner, account): payable journal items} of what is left to pay on the payslips """
        self.ensure_one()
        groups = defaultdict(lambda: self.env['account.move.line'])
        for slip in self.payslip_ids:
            partner = slip.employee_id.work_contact_id
            for line in slip._get_salary_payable_lines().filtered(lambda line: not line.reconciled):
                groups[partner, line.account_id] |= line
        return groups

    @api.depends('payslip_ids')
    def _compute_amounts(self):
        for wizard in self:
            groups = wizard._get_payment_groups()
            wizard.total_amount = -sum(sum(lines.mapped('amount_residual')) for lines in groups.values())
            wizard.employee_count = len(wizard.payslip_ids.employee_id)
            wizard.can_edit_amount = len(groups) == 1

    @api.depends('total_amount')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = wizard.total_amount

    def _check_payslips(self):
        self.ensure_one()
        not_payable = self.payslip_ids.filtered(lambda slip: not slip._can_register_payment())
        if not_payable:
            raise UserError(_('These payslips cannot be paid: %s. Only the confirmed payslips with a posted entry '
                              'that are not paid yet are paid, not the refunds.',
                              ', '.join(not_payable.mapped(lambda slip: slip.number or slip.name))))
        without_partner = self.payslip_ids.employee_id.filtered(lambda employee: not employee.work_contact_id)
        if without_partner:
            raise UserError(_('These employees have no contact to pay: %s.',
                              ', '.join(without_partner.mapped('name'))))
        for slip in self.payslip_ids:
            lines = slip._get_salary_payable_lines()
            if not lines:
                raise UserError(_('The entry of the payslip %s has no net salary to pay: set a credit account on '
                                  'the net salary rule.', slip.number or slip.name))
            not_reconcilable = lines.account_id.filtered(lambda account: not account.reconcile)
            if not_reconcilable:
                raise UserError(_('The account %(account)s of the net salary does not allow reconciliation: enable '
                                  'it on the account to pay the payslip %(payslip)s.',
                                  account=not_reconcilable[0].display_name, payslip=slip.number or slip.name))

    def action_create_payments(self):
        self.ensure_one()
        self._check_payslips()
        groups = {key: lines for key, lines in self._get_payment_groups().items()
                  if self.currency_id.compare_amounts(-sum(lines.mapped('amount_residual')), 0) > 0}
        if not groups:
            raise UserError(_('Nothing is left to pay on these payslips.'))
        if self.can_edit_amount and self.currency_id.compare_amounts(self.amount, 0) <= 0:
            raise UserError(_('The amount to pay must be positive.'))
        if self.can_edit_amount and self.currency_id.compare_amounts(self.amount, self.total_amount) > 0:
            raise UserError(_('The amount to pay cannot be more than what is left to pay, %s.',
                              self.currency_id.format(self.total_amount)))

        to_create = []
        for (partner, account), lines in groups.items():
            slips = self.payslip_ids.filtered(lambda slip: slip.move_id in lines.move_id)
            amount = self.amount if self.can_edit_amount else -sum(lines.mapped('amount_residual'))
            to_create.append({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': partner.id,
                'amount': amount,
                'date': self.payment_date,
                'memo': self.memo or ', '.join(slip.number or slip.name for slip in slips),
                'journal_id': self.journal_id.id,
                'payment_method_line_id': self.payment_method_line_id.id,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'destination_account_id': account.id,
                'payslip_ids': [Command.set(slips.ids)],
                'lines': lines,
            })
        payments = self.env['account.payment']
        for values in to_create:
            lines = values.pop('lines')
            payment = self.env['account.payment'].create(values)
            if payment.require_partner_bank_account and not payment.partner_bank_id:
                raise UserError(_('The employee %(employee)s has no bank account to be paid with %(method)s.',
                                  employee=payment.partner_id.name, method=payment.payment_method_line_id.name))
            payment.action_post()
            if payment.move_id:
                counterpart = payment.move_id.line_ids.filtered(
                    lambda line: line.account_id == lines.account_id and not line.reconciled)
                (counterpart | lines.sudo()).reconcile()
            payments |= payment
        # the payment status of the payslips follows their reconciliation
        self.payslip_ids.invalidate_recordset(['payment_state', 'paid'])
        self.env.add_to_compute(self.payslip_ids._fields['payment_state'], self.payslip_ids)

        if len(payments) == 1:
            return {
                'name': _('Payment'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'res_id': payments.id,
            }
        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payments.ids)],
            'context': {'create': False},
        }
