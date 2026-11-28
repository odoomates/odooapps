from odoo import api, fields, models

from .commission_plan import PAID_STATES

LINE_STATES = [
    ('open', 'To Settle'),
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('paid', 'Paid'),
]
ROLES = [
    ('seller', 'Salesperson'),
    ('member', 'Team Member'),
    ('leader', 'Team Leader'),
    ('reseller', 'Reseller'),
]


class OmCommissionLine(models.Model):
    _name = 'om.commission.line'
    _description = 'Commission Line'
    _order = 'date desc, id desc'

    name = fields.Char(string='Description', required=True)
    plan_id = fields.Many2one('om.commission.plan', required=True, ondelete='restrict', index=True)
    rule_id = fields.Many2one('om.commission.rule', ondelete='set null')
    company_id = fields.Many2one('res.company', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(required=True, index=True)
    period_start = fields.Date(required=True, index=True)
    period_end = fields.Date(required=True)
    user_id = fields.Many2one('res.users', string='Salesperson', index='btree_not_null')
    partner_id = fields.Many2one('res.partner', string='Beneficiary', required=True, index=True,
                                 help='Partner the commission is paid to: the salesperson or the reseller.')
    team_id = fields.Many2one('crm.team', string='Sales Team')
    role = fields.Selection(ROLES, required=True, default='seller')
    customer_id = fields.Many2one('res.partner', string='Customer')
    product_id = fields.Many2one('product.product', string='Product')
    categ_id = fields.Many2one(related='product_id.categ_id', string='Product Category')
    quantity = fields.Float(digits='Product Unit')
    base_amount = fields.Monetary(string='Revenue')
    margin_amount = fields.Monetary(string='Margin')
    rate = fields.Float(string='Rate (%)', digits=(16, 2), aggregator=None)
    amount = fields.Monetary(string='Commission')
    move_id = fields.Many2one('account.move', string='Invoice', ondelete='set null', index='btree_not_null')
    order_id = fields.Many2one('sale.order', string='Sales Order', ondelete='set null', index='btree_not_null')
    source_key = fields.Char(index=True, readonly=True)
    statement_id = fields.Many2one('om.commission.statement', ondelete='set null', index='btree_not_null')
    state = fields.Selection(LINE_STATES, string='Status', compute='_compute_state', store=True, index=True)
    is_clawback = fields.Boolean(string='Clawback',
                                 help='Takes back a commission already approved or paid.')
    capped = fields.Boolean(help='Reduced by the cap of the plan.')
    origin_line_id = fields.Many2one('om.commission.line', string='Taken Back Line', ondelete='set null')
    clawback_line_ids = fields.One2many('om.commission.line', 'origin_line_id')

    @api.depends('statement_id', 'statement_id.state')
    def _compute_state(self):
        for line in self:
            state = line.statement_id.state
            line.state = state if state in ('draft', 'approved', 'paid') else 'open'

    def _get_holder(self):
        """The salesperson, team or reseller whose achievement the line counts for."""
        self.ensure_one()
        plan_type = self.plan_id.plan_type
        if plan_type == 'team':
            return self.team_id
        if plan_type == 'partner':
            return self.partner_id
        return self.user_id

    def _is_source_valid(self):
        """Whether the invoice or order of the line still counts for the commission."""
        self.ensure_one()
        if self.move_id:
            move = self.move_id
            if move.state != 'posted':
                return False
            return self.plan_id.invoice_state != 'paid' or move.payment_state in PAID_STATES
        if self.order_id and self.source_key.startswith('sol,'):
            return self.order_id.state == 'sale'
        return not self.source_key.startswith(('aml,', 'sol,'))

    def _attach_to_draft_statements(self):
        """Add lines to settle to the draft statement of their beneficiary that covers their date."""
        lines = self.filtered(lambda line: line.state == 'open')
        if not lines:
            return
        statements = self.env['om.commission.statement'].sudo().search([
            ('state', '=', 'draft'),
            ('partner_id', 'in', lines.partner_id.ids),
            ('company_id', 'in', lines.company_id.ids),
        ], order='date_to')
        for line in lines:
            statement = statements.filtered(
                lambda s: s.partner_id == line.partner_id and s.user_id == line.user_id
                and s.company_id == line.company_id and s.date_to >= line.date)[:1]
            if statement:
                line.statement_id = statement

    def action_open_source(self):
        self.ensure_one()
        record = self.move_id or self.order_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'views': [(False, 'form')],
        }
