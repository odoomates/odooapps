from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tools import format_date

STATEMENT_STATES = [
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('paid', 'Paid'),
    ('cancel', 'Cancelled'),
]


class OmCommissionStatement(models.Model):
    _name = 'om.commission.statement'
    _description = 'Commission Statement'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: self.env._('New'))
    user_id = fields.Many2one('res.users', string='Salesperson', index='btree_not_null', tracking=True,
                              domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Beneficiary', required=True, index=True, tracking=True,
                                 help='The commission is paid to this partner.')
    beneficiary_type = fields.Selection([
        ('user', 'Salesperson'),
        ('partner', 'Reseller'),
    ], compute='_compute_beneficiary_type', store=True)
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    line_ids = fields.One2many('om.commission.line', 'statement_id', string='Commission Lines')
    line_count = fields.Integer(compute='_compute_amounts', store=True)
    amount_commission = fields.Monetary(string='Commissions', compute='_compute_amounts', store=True)
    amount_clawback = fields.Monetary(string='Clawbacks', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='Total', compute='_compute_amounts', store=True, tracking=True)
    state = fields.Selection(
        STATEMENT_STATES, string='Status', default='draft', required=True, copy=False, tracking=True,
        compute='_compute_state', store=True, readonly=False, index=True)
    payout_method = fields.Selection([
        ('bill', 'Vendor Bill'),
        ('manual', 'Other'),
    ], string='Payout', required=True, default='bill', tracking=True,
        help='Vendor Bill: the accounting creates a vendor bill for the beneficiary, and the statement is paid '
             'when the bill is paid. Other: mark the statement as paid once the commission is paid, for '
             'example with the salary.')
    move_id = fields.Many2one('account.move', string='Vendor Bill', copy=False, readonly=True,
                              index='btree_not_null')
    bill_payment_state = fields.Selection(related='move_id.payment_state', string='Bill Payment')
    approved_user_id = fields.Many2one('res.users', string='Approved By', copy=False, readonly=True)
    approved_date = fields.Date(string='Approved On', copy=False, readonly=True)
    paid_date = fields.Date(string='Paid On', copy=False, compute='_compute_paid_date', store=True)
    note = fields.Html()

    @api.depends('user_id')
    def _compute_beneficiary_type(self):
        for statement in self:
            statement.beneficiary_type = 'user' if statement.user_id else 'partner'

    @api.depends('line_ids.amount', 'line_ids.is_clawback')
    def _compute_amounts(self):
        for statement in self:
            clawback = sum(statement.line_ids.filtered('is_clawback').mapped('amount'))
            total = sum(statement.line_ids.mapped('amount'))
            statement.line_count = len(statement.line_ids)
            statement.amount_clawback = clawback
            statement.amount_commission = total - clawback
            statement.amount_total = total

    @api.depends('move_id.payment_state', 'move_id.state')
    def _compute_state(self):
        for statement in self:
            move = statement.move_id
            if not move or statement.state in ('draft', 'cancel'):
                statement.state = statement.state or 'draft'
            elif move.state == 'posted' and move.payment_state in ('paid', 'in_payment'):
                statement.state = 'paid'
            elif statement.state == 'paid':
                statement.state = 'approved'

    @api.depends('state')
    def _compute_paid_date(self):
        for statement in self:
            if statement.state != 'paid':
                statement.paid_date = False
            elif not statement.paid_date:
                statement.paid_date = fields.Date.context_today(statement)

    def _compute_access_url(self):
        super()._compute_access_url()
        for statement in self:
            statement.access_url = f'/my/commissions/{statement.id}'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].with_company(
                    vals.get('company_id') or self.env.company.id).next_by_code('om.commission.statement') \
                    or self.env._('New')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if any(statement.state in ('approved', 'paid') for statement in self):
            raise UserError(self.env._('Approved or paid statements cannot be deleted: cancel them first.'))

    def _get_report_base_filename(self):
        self.ensure_one()
        return self.env._('Commission Statement - %(name)s', name=self.name)

    # ------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------

    def _check_manager(self):
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise AccessError(self.env._('Only sales managers can approve commission statements.'))

    def action_approve(self):
        self._check_manager()
        for statement in self:
            if statement.state != 'draft':
                raise UserError(self.env._('Only draft statements can be approved.'))
            if not statement.line_ids:
                raise UserError(self.env._('The statement %(name)s has no commission lines.', name=statement.name))
        self.write({
            'state': 'approved',
            'approved_user_id': self.env.user.id,
            'approved_date': fields.Date.context_today(self),
        })
        return True

    def action_reset_draft(self):
        self._check_manager()
        for statement in self:
            if statement.move_id and statement.move_id.state != 'cancel':
                raise UserError(self.env._(
                    'Cancel the vendor bill %(bill)s before resetting the statement %(name)s to draft.',
                    bill=statement.move_id.display_name, name=statement.name))
        self.write({'state': 'draft', 'move_id': False, 'approved_user_id': False, 'approved_date': False})
        return True

    def action_cancel(self):
        self._check_manager()
        for statement in self:
            if statement.move_id and statement.move_id.state != 'cancel':
                raise UserError(self.env._(
                    'Cancel the vendor bill %(bill)s before cancelling the statement %(name)s.',
                    bill=statement.move_id.display_name, name=statement.name))
        self.line_ids.write({'statement_id': False})
        self.write({'state': 'cancel', 'move_id': False})
        return True

    def action_mark_paid(self):
        self._check_manager()
        for statement in self:
            if statement.state != 'approved' or statement.payout_method != 'manual':
                raise UserError(self.env._(
                    'Only approved statements paid outside a vendor bill can be marked as paid.'))
        self.write({'state': 'paid'})
        return True

    def _get_bill_values(self):
        self.ensure_one()
        company = self.company_id
        product = company.om_commission_product_id
        if not product:
            raise UserError(self.env._(
                'Set the commission product in the settings of the sales commissions first.'))
        journal = company.om_commission_journal_id or self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(company),
            ('type', '=', 'purchase'),
        ], limit=1)
        if not journal:
            raise UserError(self.env._('Create a purchase journal to bill the commissions.'))
        sign = -1 if self.amount_total < 0 else 1
        totals = defaultdict(float)
        for line in self.line_ids:
            totals[line.plan_id] += line.amount
        period = f'{format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}'
        invoice_lines = []
        for plan, amount in totals.items():
            if self.currency_id.is_zero(amount):
                continue
            line_vals = {
                'product_id': product.id,
                'name': self.env._('Commissions %(plan)s, %(period)s', plan=plan.name, period=period),
                'quantity': 1,
                'price_unit': amount * sign,
                'tax_ids': [Command.clear()],
            }
            if company.om_commission_account_id:
                line_vals['account_id'] = company.om_commission_account_id.id
            invoice_lines.append(Command.create(line_vals))
        return {
            'move_type': 'in_refund' if sign < 0 else 'in_invoice',
            'partner_id': self.partner_id.id,
            'company_id': company.id,
            'journal_id': journal.id,
            'currency_id': self.currency_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'ref': self.name,
            'invoice_line_ids': invoice_lines,
        }

    def action_create_bill(self):
        if not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(self.env._('Only invoicing users can create the vendor bills of commissions.'))
        for statement in self:
            if statement.state != 'approved' or statement.payout_method != 'bill':
                raise UserError(self.env._('Create vendor bills for approved statements paid by vendor bill.'))
            if statement.move_id and statement.move_id.state != 'cancel':
                raise UserError(self.env._('The statement %(name)s already has a vendor bill.', name=statement.name))
            if statement.currency_id.is_zero(statement.amount_total):
                raise UserError(self.env._('The statement %(name)s has nothing to pay.', name=statement.name))
            move = self.env['account.move'].with_company(statement.company_id).create(statement._get_bill_values())
            statement.move_id = move
            move.message_post_with_source(
                'mail.message_origin_link',
                render_values={'self': move, 'origin': statement},
                subtype_xmlid='mail.mt_note',
            )
        return self.action_view_bill() if len(self) == 1 else True

    def action_view_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'views': [(False, 'form')],
        }

    def action_view_lines(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_commission.action_commission_line')
        action['domain'] = [('statement_id', '=', self.id)]
        action['context'] = {}
        return action

    # ------------------------------------------------------------
    # Payout hook
    # ------------------------------------------------------------

    @api.model
    def _get_payable_amounts(self, date_from=None, date_to=None, users=None, company=None):
        """Approved commissions not paid by vendor bill and not paid yet, per salesperson.

        Used to pay commissions with another tool, such as payslips: returns a dict
        {res.users record: (amount, statements)} for the statements that end between the two dates.
        Mark the statements as paid with :meth:`_set_paid_externally` once they are paid.
        """
        domain = [('state', '=', 'approved'), ('payout_method', '=', 'manual'), ('user_id', '!=', False)]
        if date_from:
            domain.append(('date_to', '>=', date_from))
        if date_to:
            domain.append(('date_to', '<=', date_to))
        if users is not None:
            domain.append(('user_id', 'in', users.ids))
        if company:
            domain.append(('company_id', '=', company.id))
        result = {}
        for statement in self.search(domain):
            amount, statements = result.get(statement.user_id, (0.0, self.browse()))
            result[statement.user_id] = (amount + statement.amount_total, statements | statement)
        return result

    def _set_paid_externally(self, paid_date=None):
        statements = self.filtered(lambda s: s.state == 'approved')
        statements.write({'state': 'paid'})
        if paid_date:
            statements.paid_date = paid_date
