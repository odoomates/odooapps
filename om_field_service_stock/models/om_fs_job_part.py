from odoo import api, fields, models
from odoo.exceptions import UserError


class OmFsJobPart(models.Model):
    _name = 'om.fs.job.part'
    _description = "Part Used on a Field Service Job"
    _order = 'task_id, sequence, id'

    task_id = fields.Many2one('project.task', string="Job", required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', string="Product", required=True,
                                 domain="[('type', '=', 'consu')]")
    tracking = fields.Selection(related='product_id.tracking', string="Tracking")
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit', required=True)
    product_uom_id = fields.Many2one('uom.uom', string="Unit", compute='_compute_product_uom_id', store=True, precompute=True,
                                     readonly=False, required=True)
    location_id = fields.Many2one(
        'stock.location', string="Taken From", compute='_compute_location_id', store=True, precompute=True, readonly=False,
        required=True, domain="[('usage', '=', 'internal')]",
        help="The van of the technician, or a warehouse.")
    lot_id = fields.Many2one('stock.lot', string="Lot/Serial Number",
                             domain="[('product_id', '=', product_id)]")
    install_on_site = fields.Boolean(
        string="Installed at Site", compute='_compute_install_on_site', store=True, precompute=True, readonly=False,
        help="The serial number is recorded in the equipment of the customer site when the job is done.")
    move_id = fields.Many2one('stock.move', string="Stock Move", readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'To Do'),
        ('done', 'Done'),
    ], string="Status", default='draft', required=True, copy=False)
    company_id = fields.Many2one(related='task_id.company_id', store=True, string="Company")

    _check_quantity = models.Constraint(
        'CHECK(quantity > 0)',
        'The quantity of a part must be positive.',
    )

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for part in self:
            part.product_uom_id = part.product_id.uom_id

    @api.depends('task_id')
    def _compute_location_id(self):
        for part in self:
            if not part.location_id:
                part.location_id = part.task_id._fs_default_part_location()

    @api.depends('product_id.tracking')
    def _compute_install_on_site(self):
        for part in self:
            part.install_on_site = part.product_id.tracking == 'serial'

    @api.ondelete(at_uninstall=False)
    def _unlink_except_done(self):
        if any(part.state == 'done' for part in self):
            raise UserError(self.env._("A part already taken out of stock cannot be removed."))

    def write(self, vals):
        if any(part.state == 'done' for part in self) and \
                set(vals) & {'product_id', 'quantity', 'lot_id', 'location_id', 'product_uom_id'}:
            raise UserError(self.env._("A part already taken out of stock cannot be changed."))
        return super().write(vals)

    def _fs_mobile_data(self):
        return [{
            'id': part.id,
            'product': part.product_id.display_name,
            'quantity': part.quantity,
            'uom': part.product_uom_id.name,
            'lot': part.lot_id.name or '',
            'location': part.location_id.display_name,
            'done': part.state == 'done',
        } for part in self]
