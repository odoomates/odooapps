from odoo import fields, models

HR = 'hr.group_hr_user'


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee', 'om.pos.access.rules']

    om_pos_own_rules = fields.Boolean(
        string='Own Point of Sale Rules', groups=HR,
        help="When this employee is the cashier, the rules below apply. Off, they follow the rules of their Odoo "
             "user, or else of the Odoo user who opened the shop.")
    # private to HR, as the other fields of an employee missing from their public profile: the shop never
    # reads them, the server sends it the rules of each cashier
    om_pos_no_refund = fields.Boolean(groups=HR)
    om_pos_no_discount = fields.Boolean(groups=HR)
    om_pos_max_discount = fields.Float(groups=HR)
    om_pos_no_price_change = fields.Boolean(groups=HR)
    om_pos_max_price_cut = fields.Float(groups=HR)
    om_pos_no_cash_move = fields.Boolean(groups=HR)
    om_pos_no_close = fields.Boolean(groups=HR)
    om_pos_no_partner_edit = fields.Boolean(groups=HR)
    om_pos_no_decrease = fields.Boolean(groups=HR)
    om_pos_payment_method_ids = fields.Many2many(groups=HR)
    om_pos_no_below_cost = fields.Boolean(groups=HR)
