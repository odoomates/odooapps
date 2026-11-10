from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_deferred_expense_journal_id = fields.Many2one(related='company_id.om_deferred_expense_journal_id', readonly=False)
    om_deferred_expense_account_id = fields.Many2one(related='company_id.om_deferred_expense_account_id', readonly=False)
    om_deferred_expense_method = fields.Selection(related='company_id.om_deferred_expense_method', readonly=False)
    om_deferred_expense_generation = fields.Selection(related='company_id.om_deferred_expense_generation', readonly=False)
    om_deferred_expense_periodicity = fields.Selection(related='company_id.om_deferred_expense_periodicity', readonly=False)
    om_deferred_revenue_journal_id = fields.Many2one(related='company_id.om_deferred_revenue_journal_id', readonly=False)
    om_deferred_revenue_account_id = fields.Many2one(related='company_id.om_deferred_revenue_account_id', readonly=False)
    om_deferred_revenue_method = fields.Selection(related='company_id.om_deferred_revenue_method', readonly=False)
    om_deferred_revenue_generation = fields.Selection(related='company_id.om_deferred_revenue_generation', readonly=False)
    om_deferred_revenue_periodicity = fields.Selection(related='company_id.om_deferred_revenue_periodicity', readonly=False)
