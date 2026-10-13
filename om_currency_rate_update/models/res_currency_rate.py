from odoo import fields, models

RATE_FIELDS = {'rate', 'company_rate', 'inverse_company_rate'}


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    rate_source = fields.Char(string='Source', readonly=True,
                              help="Where the rate comes from; empty when entered by hand.")

    def write(self, vals):
        if RATE_FIELDS & set(vals) and 'rate_source' not in vals:
            # changed by hand
            vals = dict(vals, rate_source=False)
        return super().write(vals)
