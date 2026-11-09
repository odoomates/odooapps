from odoo import fields, models


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'om.pos.access.rules']

    om_pos_pricelist_ids = fields.Many2many(
        relation='om_pos_access_user_pricelist_rel', column1='user_id', column2='pricelist_id')
