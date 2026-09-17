from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrSalaryBracket(models.Model):
    """ A scale of bands the salary rules compute an amount from, e.g. the income tax of a country.

    The bands are held by date, and by key when the same tax has a table per filing status, per state or per
    pay frequency, so that a rule stays one line whatever the country asks for.
    """
    _name = 'hr.salary.bracket'
    _description = 'Salary Bracket'
    _order = 'code'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help='The name the salary rules read the bracket by, e.g. INCOME_TAX for brackets.INCOME_TAX.')
    computation = fields.Selection([
        ('marginal', 'Marginal: each band on its own slice'),
        ('excess', 'Excess: the fixed amount of the band, plus its rate on what exceeds it'),
        ('flat', 'Flat: the rate of the band on the whole amount'),
    ], required=True, default='marginal', help=(
        'Marginal taxes each slice at the rate of its band, as the income tax of most countries does.\n'
        'Excess takes the fixed amount of the band the amount falls in, plus the rate of that band on what '
        'exceeds its floor.\n'
        'Flat applies the rate of the band the amount falls in to the whole amount.'))
    version_ids = fields.One2many('hr.salary.bracket.version', 'bracket_id', string='Tables')
    company_id = fields.Many2one(
        'res.company', string='Company',
        help='Leave empty for a bracket shared by every company.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Description')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'The code of a salary bracket must be unique per company.',
    )

    @api.constrains('code')
    def _check_code(self):
        for bracket in self:
            if not (bracket.code or '').isidentifier():
                raise ValidationError(_(
                    'The code %s cannot be used: write a code starting with a letter and made of letters, '
                    'digits and underscores, e.g. INCOME_TAX.', bracket.code))

    @api.depends('code')
    def _compute_display_name(self):
        for bracket in self:
            bracket.display_name = f'[{bracket.code}] {bracket.name}' if bracket.code else bracket.name

    @api.model
    def _get_bracket(self, code, company=None):
        company = company or self.env.company
        return self.search(
            [('code', '=', code), ('company_id', 'in', (company.id, False))], order='company_id', limit=1)

    def _get_version(self, date, key=False):
        """ :return: the table of the bracket that applies on `date` for `key` """
        self.ensure_one()
        # sorted here and not left to the order of the model: the tables just written are not sorted yet
        versions = self.version_ids.filtered(
            lambda version: version.date_from <= date and (version.key or False) == (key or False)
        ).sorted('date_from', reverse=True)
        if not versions:
            raise UserError(_(
                'The salary bracket %(code)s has no table on %(date)s%(key)s: add it in '
                'Payroll > Configuration > Salary Brackets.',
                code=self.code, date=date, key=_(' for %s', key) if key else ''))
        return versions[0]

    def compute(self, base, date, key=False):
        """ :return: the amount the bands give for `base`, always a positive number

        A salary rule deducting it makes it negative itself, so that what the bracket does stays readable.
        """
        self.ensure_one()
        return self._get_version(date, key)._compute(base, self.computation)


class HrSalaryBracketVersion(models.Model):
    """ The bands of a bracket from a date on, for one key. """
    _name = 'hr.salary.bracket.version'
    _description = 'Salary Bracket Table'
    _order = 'date_from desc, key'

    bracket_id = fields.Many2one(
        'hr.salary.bracket', string='Bracket', required=True, ondelete='cascade', index=True)
    date_from = fields.Date(string='From', required=True, default=fields.Date.context_today)
    key = fields.Char(
        string='Key',
        help='The variant of the table, when a tax has one per filing status, per state or per pay '
             'frequency, e.g. SINGLE. Leave empty when there is only one table.')
    line_ids = fields.One2many('hr.salary.bracket.line', 'version_id', string='Bands')
    company_id = fields.Many2one(related='bracket_id.company_id', store=True)

    _bracket_date_key_uniq = models.Constraint(
        'unique(bracket_id, date_from, key)',
        'A salary bracket can only have one table per date and key.',
    )

    @api.depends('date_from', 'key')
    def _compute_display_name(self):
        for version in self:
            version.display_name = f'{version.date_from} {version.key}' if version.key else str(version.date_from)

    def _compute(self, base, computation):
        """ :return: what the bands give for `base` """
        self.ensure_one()
        bands = self.line_ids.sorted('lower')
        if not bands:
            return 0.0
        if computation == 'marginal':
            amount = 0.0
            for band in bands:
                upper = band.upper or float('inf')
                slice_amount = min(base, upper) - band.lower
                if slice_amount > 0:
                    amount += slice_amount * band.rate / 100.0
            band = self._band_of(base, bands)
            return amount + band.fixed_amount
        band = self._band_of(base, bands)
        if computation == 'excess':
            return band.fixed_amount + (base - band.lower) * band.rate / 100.0
        return band.fixed_amount + base * band.rate / 100.0

    @api.model
    def _band_of(self, base, bands):
        """ :return: the band `base` falls in, the last one when it is above every band """
        for band in bands:
            upper = band.upper or float('inf')
            if band.lower <= base <= upper:
                return band
        return bands[-1] if base > bands[-1].lower else bands[0]


class HrSalaryBracketLine(models.Model):
    """ One band of a bracket table. """
    _name = 'hr.salary.bracket.line'
    _description = 'Salary Bracket Band'
    _order = 'lower'

    version_id = fields.Many2one(
        'hr.salary.bracket.version', string='Table', required=True, ondelete='cascade', index=True)
    lower = fields.Float(string='From', digits='Payroll')
    upper = fields.Float(string='To', digits='Payroll', help='Leave at zero for the last band, which has no limit.')
    rate = fields.Float(string='Rate (%)', digits='Payroll Rate')
    fixed_amount = fields.Float(string='Fixed Amount', digits='Payroll')
    company_id = fields.Many2one(related='version_id.company_id', store=True)

    @api.constrains('lower', 'upper')
    def _check_bounds(self):
        for band in self:
            if band.upper and band.upper <= band.lower:
                raise ValidationError(_(
                    'The band from %(lower)s ends at %(upper)s, before it starts.',
                    lower=band.lower, upper=band.upper))


class SalaryBrackets:
    """ Gives the salary rules the brackets as ``brackets.INCOME_TAX.compute(base)``. """

    def __init__(self, env, date, company):
        self.env = env
        self.date = date
        self.company = company

    def __getattr__(self, code):
        bracket = self.env['hr.salary.bracket']._get_bracket(code, self.company)
        if not bracket:
            raise UserError(_(
                'No salary bracket %(code)s: create it in Payroll > Configuration > Salary Brackets, '
                'or correct the salary rule reading it.', code=code))
        return BracketHandle(bracket, self.date)


class BracketHandle:
    """ One bracket, ready to compute on the date of the payslip. """

    def __init__(self, bracket, date):
        self.bracket = bracket
        self.date = date

    def compute(self, base, key=False):
        return self.bracket.compute(base, self.date, key=key)
