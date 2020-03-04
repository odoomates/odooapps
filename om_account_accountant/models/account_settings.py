# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fiscalyear_last_day = fields.Integer(related='company_id.fiscalyear_last_day', readonly=False)
    fiscalyear_last_month = fields.Selection([(1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'), (5, 'May'),
                                              (6, 'June'), (7, 'July'), (8, 'August'), (9, 'September'),
                                              (10, 'October'), (11, 'November'), (12, 'December')],
                                             related='company_id.fiscalyear_last_month', readonly=False)
    period_lock_date = fields.Date(related='company_id.period_lock_date', readonly=False)
    fiscalyear_lock_date = fields.Date(related='company_id.fiscalyear_lock_date', readonly=False)
