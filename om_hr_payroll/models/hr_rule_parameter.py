from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrRuleParameter(models.Model):
    """ A value the salary rules read by name, kept by date.

    Rates, thresholds and ceilings change every year. Holding them here instead of in the code of a rule
    means an accountant changes them, the change is dated, and a payslip computed again for an old period is
    still computed with the value of that period.
    """
    _name = 'hr.rule.parameter'
    _description = 'Salary Rule Parameter'
    _order = 'code'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help='The name the salary rules read the parameter by, e.g. SS_RATE for parameters.SS_RATE.')
    value_type = fields.Selection([
        ('number', 'Number'),
        ('text', 'Text'),
    ], required=True, default='number')
    value_ids = fields.One2many('hr.rule.parameter.value', 'parameter_id', string='Values')
    company_id = fields.Many2one(
        'res.company', string='Company',
        help='Leave empty for a parameter shared by every company.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Description')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'The code of a rule parameter must be unique per company.',
    )

    @api.constrains('code')
    def _check_code(self):
        for parameter in self:
            if not (parameter.code or '').isidentifier():
                raise ValidationError(_(
                    'The code %s cannot be used: write a code starting with a letter and made of letters, '
                    'digits and underscores, e.g. SS_RATE.', parameter.code))

    @api.depends('code')
    def _compute_display_name(self):
        for parameter in self:
            parameter.display_name = f'[{parameter.code}] {parameter.name}' if parameter.code else parameter.name

    @api.model
    def _get_parameter(self, code, company=None):
        """ :return: the parameter of this code for the company, the shared one otherwise """
        company = company or self.env.company
        domain = [('code', '=', code), ('company_id', 'in', (company.id, False))]
        # the parameter of the company wins over the one shared by the companies
        return self.search(domain, order='company_id', limit=1)

    @api.model
    def get_value(self, code, date, company=None):
        """ :return: the value of the parameter `code` on `date`

        A missing parameter, or one with no value yet on that date, raises: a rate silently worth zero is a
        payslip that is wrong without saying so.
        """
        parameter = self._get_parameter(code, company)
        if not parameter:
            raise UserError(_(
                'No rule parameter %(code)s: create it in Payroll > Configuration > Rule Parameters, '
                'or correct the salary rule reading it.', code=code))
        return parameter._value_at(date)

    def _value_at(self, date):
        self.ensure_one()
        # sorted here and not left to the order of the model: the values just written are not sorted yet
        value = self.value_ids.filtered(
            lambda value: value.date_from <= date).sorted('date_from', reverse=True)[:1]
        if not value:
            raise UserError(_(
                'The rule parameter %(code)s has no value on %(date)s: add the value that applies from that '
                'date in Payroll > Configuration > Rule Parameters.', code=self.code, date=date))
        return value.value_number if self.value_type == 'number' else value.value_text


class HrRuleParameterValue(models.Model):
    """ What a rule parameter is worth from a date on. """
    _name = 'hr.rule.parameter.value'
    _description = 'Salary Rule Parameter Value'
    _order = 'date_from desc'

    parameter_id = fields.Many2one(
        'hr.rule.parameter', string='Parameter', required=True, ondelete='cascade', index=True)
    date_from = fields.Date(string='From', required=True, default=fields.Date.context_today)
    value_type = fields.Selection(related='parameter_id.value_type')
    value_number = fields.Float(string='Value', digits=(16, 6))
    value_text = fields.Char(string='Text Value')

    _parameter_date_uniq = models.Constraint(
        'unique(parameter_id, date_from)',
        'A rule parameter can only have one value per date.',
    )


class RuleParameters:
    """ Gives the salary rules the parameters as ``parameters.SS_RATE``, on the date of the payslip. """

    def __init__(self, env, date, company):
        self.env = env
        self.date = date
        self.company = company

    def __getattr__(self, code):
        return self.env['hr.rule.parameter'].get_value(code, self.date, self.company)

    def get(self, code, default=None):
        """ :return: the value of the parameter, or `default` when there is none

        For the rules that may run without the parameter being configured. Prefer ``parameters.CODE``, which
        says what is missing instead of paying a wrong amount quietly.
        """
        try:
            return self.__getattr__(code)
        except UserError:
            return default
