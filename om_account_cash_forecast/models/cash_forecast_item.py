from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

RECURRENCE_STEPS = {
    'weekly': relativedelta(weeks=1),
    'monthly': relativedelta(months=1),
    'quarterly': relativedelta(months=3),
    'yearly': relativedelta(years=1),
}


class AccountCashForecastItem(models.Model):
    _name = 'account.cash.forecast.item'
    _description = 'Cash Forecast Item'
    _order = 'date, id'
    _check_company_auto = True

    name = fields.Char(string='Description', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    direction = fields.Selection(
        [('in', 'Receipt'), ('out', 'Payment')], string='Type', required=True, default='out')
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', required=True, default=lambda self: self.env.company.currency_id,
        help="Converted to the currency of the company at the rate of the day of the forecast.")
    date = fields.Date(string='Expected On', required=True, default=fields.Date.context_today)
    recurrence = fields.Selection(
        [('none', 'Once'), ('weekly', 'Every Week'), ('monthly', 'Every Month'),
         ('quarterly', 'Every Quarter'), ('yearly', 'Every Year')],
        required=True, default='none')
    date_end = fields.Date(string='Until', help="Leave empty to repeat without end.")
    partner_id = fields.Many2one('res.partner', string='Partner', check_company=True)
    note = fields.Text()

    @api.constrains('amount', 'date', 'date_end')
    def _check_values(self):
        for item in self:
            if item.currency_id.compare_amounts(item.amount, 0.0) <= 0:
                raise ValidationError(_('The amount of the expected item "%s" must be positive.', item.name))
            if item.date_end and item.date_end < item.date:
                raise ValidationError(_('The expected item "%s" ends before it starts.', item.name))

    def _get_occurrences(self, date_from, date_to):
        """ :return: the dates of the item between `date_from` and `date_to` """
        self.ensure_one()
        if self.recurrence == 'none':
            return [self.date] if date_from <= self.date <= date_to else []
        step = RECURRENCE_STEPS[self.recurrence]
        last = min(date_to, self.date_end) if self.date_end else date_to
        dates = []
        index = 0
        occurrence = self.date
        while occurrence <= last:
            if occurrence >= date_from:
                dates.append(occurrence)
            index += 1
            # from the first date each time, so that the 31st stays the end of the month
            occurrence = self.date + step * index
        return dates
