from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_user_rel', 'user_id', 'menu_id', string='Hidden Menus',
        groups='base.group_system',
        help="These menus and their sub-menus are hidden for the user, in every company.")
