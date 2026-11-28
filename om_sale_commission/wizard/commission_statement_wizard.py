from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils


class OmCommissionStatementWizard(models.TransientModel):
    _name = 'om.commission.statement.wizard'
    _description = 'Create Commission Statements'

    @api.model
    def _default_date_to(self):
        return date_utils.start_of(fields.Date.context_today(self), 'month') - timedelta(days=1)

    date_from = fields.Date(string='From', required=True,
                            default=lambda self: date_utils.start_of(self._default_date_to(), 'month'))
    date_to = fields.Date(string='Up To', required=True, default=_default_date_to,
                          help='Every commission line not settled yet, dated up to this day, goes into the '
                               'statement of its beneficiary.')
    recompute = fields.Boolean(string='Recompute First', default=True,
                               help='Recompute the commissions of the period before creating the statements.')
    beneficiary = fields.Selection([
        ('all', 'Salespersons and Resellers'),
        ('user', 'Salespersons'),
        ('partner', 'Resellers'),
    ], required=True, default='all')
    payout_method = fields.Selection([
        ('bill', 'Vendor Bill'),
        ('manual', 'Other'),
    ], string='Payout', required=True, default='bill')

    def action_create(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(self.env._('The start date must come before the end date.'))
        companies = self.env.companies
        if self.recompute:
            plans = self.env['om.commission.plan'].search([('company_id', 'in', companies.ids)])
            plans._compute_commissions(self.date_from, self.date_to)
        domain = [('state', '=', 'open'), ('date', '<=', self.date_to), ('company_id', 'in', companies.ids)]
        if self.beneficiary == 'user':
            domain.append(('user_id', '!=', False))
        elif self.beneficiary == 'partner':
            domain.append(('user_id', '=', False))
        groups = defaultdict(lambda: self.env['om.commission.line'])
        for line in self.env['om.commission.line'].search(domain):
            groups[(line.company_id, line.user_id, line.partner_id)] |= line
        statements = self.env['om.commission.statement']
        for (company, user, partner), lines in groups.items():
            statement = statements.create({
                'company_id': company.id,
                'user_id': user.id,
                'partner_id': partner.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'payout_method': self.payout_method,
            })
            lines.statement_id = statement
            statements |= statement
        if not statements:
            raise UserError(self.env._('There is no commission to settle up to this date.'))
        action = self.env['ir.actions.act_window']._for_xml_id('om_sale_commission.action_commission_statement')
        action['domain'] = [('id', 'in', statements.ids)]
        return action
