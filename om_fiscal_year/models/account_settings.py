from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fiscalyear_last_day = fields.Integer(
        related='company_id.fiscalyear_last_day', readonly=False, string='Fiscal Year Last Day'
    )
    fiscalyear_last_month = fields.Selection(
        related='company_id.fiscalyear_last_month', readonly=False, string='Fiscal Year Last Month'
    )
    tax_lock_date = fields.Date(
        related='company_id.hard_lock_date', readonly=False, string='Tax Lock Date'
    )
    sale_lock_date = fields.Date(
        related='company_id.hard_lock_date', readonly=False, string='Sale Lock Date'
    )
    purchase_lock_date = fields.Date(
        related='company_id.hard_lock_date', readonly=False, string='Purchase Lock Date'
    )
    hard_lock_date = fields.Date(
        related='company_id.hard_lock_date', readonly=False, string='Hard Lock Date'
    )
    fiscalyear_lock_date = fields.Date(
        related='company_id.fiscalyear_lock_date', readonly=False, string='Fiscal Year Lock Date'
    )
    group_fiscal_year = fields.Boolean(
        string='Fiscal Years', implied_group='om_fiscal_year.group_fiscal_year'
    )
