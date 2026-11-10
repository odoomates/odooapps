from odoo import fields, models


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'om.pos.access.rules']

    om_pos_pricelist_ids = fields.Many2many(
        relation='om_pos_access_user_pricelist_rel', column1='user_id', column2='pricelist_id')
    # only the users of the Point of Sale may read its payment methods: the others do not see the field
    om_pos_payment_method_ids = fields.Many2many(groups='point_of_sale.group_pos_user')
