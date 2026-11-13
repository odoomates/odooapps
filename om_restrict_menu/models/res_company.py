from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_company_rel', 'company_id', 'menu_id', string='Hidden Menus',
        groups='base.group_system',
        help="These menus and their sub-menus are hidden for every user while the company is the "
             "current company.")
