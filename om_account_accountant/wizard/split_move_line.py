from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


class OmSplitMoveLine(models.TransientModel):
    """ Split a journal item over other accounts: in place on a draft entry, by a reclassification entry on a
    posted one, so that the books keep what was posted. """
    _name = 'om.split.move.line'
    _description = 'Split a Journal Item'

    line_id = fields.Many2one('account.move.line', string='Journal Item', required=True, readonly=True)
    move_id = fields.Many2one(related='line_id.move_id')
    move_state = fields.Selection(related='line_id.move_id.state')
    currency_id = fields.Many2one(related='line_id.currency_id')
    company_id = fields.Many2one(related='line_id.company_id')
    amount = fields.Monetary(string='Amount', compute='_compute_amount', currency_field='currency_id')
    mode = fields.Selection([('percent', 'Percentage'), ('amount', 'Amount')], default='percent', required=True)
    date = fields.Date(string='Reclassification Date', default=fields.Date.context_today,
                       help='The date of the entry moving the amounts of a posted journal item.')
    split_ids = fields.One2many('om.split.move.line.part', 'wizard_id', string='Split Into')
    split_total = fields.Monetary(compute='_compute_split_total', currency_field='currency_id')
    left_amount = fields.Monetary(string='Left on the Item', compute='_compute_split_total',
                                  currency_field='currency_id')

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if 'line_id' in fields and not values.get('line_id') \
                and self.env.context.get('active_model') == 'account.move.line':
            values['line_id'] = (self.env.context.get('active_ids') or [False])[0]
        return values

    @api.depends('line_id')
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = abs(wizard.line_id.amount_currency)

    @api.depends('split_ids.value', 'mode', 'amount')
    def _compute_split_total(self):
        for wizard in self:
            wizard.split_total = sum(part._amount() for part in wizard.split_ids)
            wizard.left_amount = wizard.amount - wizard.split_total

    def _check_splittable(self):
        line = self.line_id
        if line.display_type not in ('product', 'entry', False) or line.tax_line_id or line.tax_ids:
            raise UserError(_('Only journal items without taxes can be split.'))
        if line.reconciled or line.matched_debit_ids or line.matched_credit_ids:
            raise UserError(_('The journal item %s is reconciled: unreconcile it first.', line.display_name))
        if not self.split_ids:
            raise UserError(_('Add the accounts to split the journal item into.'))
        if any(part._amount() <= 0 for part in self.split_ids):
            raise UserError(_('Every part must be more than zero.'))
        if self.currency_id.compare_amounts(self.split_total, self.amount) > 0:
            raise UserError(_('The parts add up to more than the journal item.'))

    def action_split(self):
        self.ensure_one()
        self._check_splittable()
        line = self.line_id
        sign = 1 if line.amount_currency >= 0 else -1
        rate = abs(line.balance / line.amount_currency) if line.amount_currency else 1.0
        company_currency = line.company_currency_id
        parts = []
        for part in self.split_ids:
            amount_currency = sign * self.currency_id.round(part._amount())
            parts.append({
                'name': part.label or line.name,
                'account_id': part.account_id.id,
                'partner_id': (part.partner_id or line.partner_id).id,
                'analytic_distribution': part.analytic_distribution or line.analytic_distribution,
                'currency_id': line.currency_id.id,
                'amount_currency': amount_currency,
                'balance': company_currency.round(amount_currency * rate),
            })
        moved_currency = sum(vals['amount_currency'] for vals in parts)
        moved_balance = sum(vals['balance'] for vals in parts)
        if line.move_id.state == 'draft':
            line.move_id.write({'line_ids': [
                Command.update(line.id, {'amount_currency': line.amount_currency - moved_currency,
                                         'balance': line.balance - moved_balance}),
                *[Command.create(vals) for vals in parts],
            ]})
            if line.currency_id.is_zero(line.amount_currency):
                line.unlink()
            return {'type': 'ir.actions.act_window_close'}
        # a posted item stays as it is: an entry moves the parts from its account to the new ones
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': line.journal_id.id if line.journal_id.type == 'general' else self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(line.company_id), ('type', '=', 'general')],
                limit=1).id,
            'date': self.date,
            'ref': _('Split of %s', line.move_id.name),
            'line_ids': [
                Command.create({
                    'name': _('Split of %s', line.name or line.move_id.name),
                    'account_id': line.account_id.id,
                    'partner_id': line.partner_id.id,
                    'analytic_distribution': line.analytic_distribution,
                    'currency_id': line.currency_id.id,
                    'amount_currency': -moved_currency,
                    'balance': -moved_balance,
                }),
                *[Command.create(vals) for vals in parts],
            ],
        })
        move.action_post()
        line.move_id.message_post(body=_('Split by the entry %s.', move._get_html_link()))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'views': [(False, 'form')],
        }


class OmSplitMoveLinePart(models.TransientModel):
    _name = 'om.split.move.line.part'
    _description = 'Part of a Split Journal Item'
    _inherit = ['analytic.mixin']

    wizard_id = fields.Many2one('om.split.move.line', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True,
                                 domain="[('account_type', '!=', 'off_balance')]")
    partner_id = fields.Many2one('res.partner', string='Partner')
    label = fields.Char(string='Label')
    value = fields.Float(string='Percentage or Amount', required=True)

    def _amount(self):
        self.ensure_one()
        wizard = self.wizard_id
        if wizard.mode == 'percent':
            return wizard.amount * self.value / 100.0
        return self.value
