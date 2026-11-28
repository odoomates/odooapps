from odoo import fields, models


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    rental_lot_id = fields.Many2one(
        'stock.lot', string="Serial Number", index='btree_not_null', ondelete='set null',
        help="Serial number rented with this unit.")

    _unique_rental_lot = models.UniqueIndex(
        '(rental_lot_id) WHERE rental_lot_id IS NOT NULL',
        'A serial number has only one rental unit.',
    )
