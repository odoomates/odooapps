from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_adapt_role_ids = fields.Many2many(
        'res.groups', 'om_adapt_role_company_rel', 'company_id', 'group_id', string='Roles learnt apart',
        help="Each user is counted for the first of these groups they belong to, and gets the "
             "changes learnt for it on top of the changes for everyone.")
    om_adapt_pinned_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_adapt_pinned_menu_company_rel', 'company_id', 'menu_id', string='Menus kept in place',
        help="These menus never move, and no menu moves past them.")
