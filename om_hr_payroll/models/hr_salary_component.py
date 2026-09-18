from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSalaryComponent(models.Model):
    """ A part of the pay of an employee, whose amount is set on the version/contract.

    Salary rules read the amounts of the components of the version with ``components.<CODE>``, so a company
    describes its own pay structure without a field for each allowance.
    """
    _name = 'hr.salary.component'
    _inherit = ['mail.thread']
    _description = 'Salary Component'
    _order = 'sequence, code'

    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char(
        required=True,
        help='The name under which the salary rules read the component, e.g. HOUSING for components.HOUSING.', tracking=True)
    sequence = fields.Integer(default=10)
    category_id = fields.Many2one(
        'hr.salary.rule.category', string='Category',
        default=lambda self: self.env.ref('om_hr_payroll.ALW', raise_if_not_found=False),
        help='The category of the salary rule paying the component. It only documents the component: '
             'the rules decide what is computed.', tracking=True)
    default_amount = fields.Monetary(
        string='Default Amount',
        help='Proposed on the versions where the component is added. The amount of each version can be changed.', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
        compute='_compute_currency_id', store=True, readonly=False)
    active = fields.Boolean(default=True, tracking=True)
    note = fields.Text(string='Description')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'The code of a salary component must be unique per company.',
    )

    @api.depends('company_id')
    def _compute_currency_id(self):
        for component in self:
            component.currency_id = component.company_id.currency_id or self.env.company.currency_id

    @api.constrains('code')
    def _check_code(self):
        """ The code becomes an attribute of ``components`` in the salary rules, so it has to be a name Python
            accepts. """
        for component in self:
            if not (component.code or '').isidentifier():
                raise ValidationError(_(
                    'The code %s cannot be used: write a code starting with a letter and made of letters, '
                    'digits and underscores, e.g. HOUSING.', component.code))

    @api.depends('code')
    def _compute_display_name(self):
        for component in self:
            component.display_name = f'[{component.code}] {component.name}' if component.code else component.name


class HrVersionSalaryComponent(models.Model):
    """ The amount of a salary component for one version/contract of an employee. """
    _name = 'hr.version.salary.component'
    _description = 'Salary Component of a Version'
    _order = 'sequence, id'

    version_id = fields.Many2one(
        'hr.version', string='Version', required=True, ondelete='cascade', index=True)
    component_id = fields.Many2one(
        'hr.salary.component', string='Component', required=True, ondelete='restrict')
    code = fields.Char(related='component_id.code', store=True, string='Code')
    sequence = fields.Integer(related='component_id.sequence', store=True)
    amount = fields.Monetary(string='Amount')
    currency_id = fields.Many2one(related='version_id.currency_id', string='Currency')
    company_id = fields.Many2one(related='version_id.company_id', store=True, string='Company')

    _version_component_uniq = models.Constraint(
        'unique(version_id, component_id)',
        'A salary component can only be set once on a version.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """ Set the amount of the component the version already carries instead of adding it twice.

        ``hr.employee._create`` writes the values of the version a second time, after the framework has
        already created it with them, so creating an employee with its salary components would create each
        line twice. The version keeps one line per component either way.
        """
        existing = self.env['hr.version.salary.component']
        remaining = []
        for vals in vals_list:
            duplicate = self.env['hr.version.salary.component']
            if vals.get('version_id') and vals.get('component_id'):
                duplicate = self.search([
                    ('version_id', '=', vals['version_id']),
                    ('component_id', '=', vals['component_id']),
                ], limit=1)
            if duplicate:
                if 'amount' in vals:
                    duplicate.amount = vals['amount']
                existing |= duplicate
            else:
                remaining.append(vals)
        return super().create(remaining) | existing

    @api.onchange('component_id')
    def _onchange_component_id(self):
        for line in self.filtered(lambda line: not line.amount):
            line.amount = line.component_id.default_amount
