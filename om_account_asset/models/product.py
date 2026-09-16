from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    asset_category_id = fields.Many2one(
        'account.asset.category', string='Asset Type',
        company_dependent=True, ondelete="restrict"
    )
    deferred_revenue_category_id = fields.Many2one(
        'account.asset.category', string='Deferred Revenue Type',
        company_dependent=True, ondelete="restrict"
    )
