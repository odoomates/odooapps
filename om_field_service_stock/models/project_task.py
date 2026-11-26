from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class ProjectTask(models.Model):
    _inherit = 'project.task'

    part_ids = fields.One2many('om.fs.job.part', 'task_id', string="Parts", copy=False)
    fs_picking_ids = fields.One2many('stock.picking', 'fs_task_id', string="Parts Transfers")
    fs_picking_count = fields.Integer(compute='_compute_fs_picking_count', string="Transfer Count")
    equipment_id = fields.Many2one(
        'om.fs.equipment', string="Equipment Serviced", index='btree_not_null', tracking=True,
        domain="[('commercial_partner_id', '=', commercial_partner_id)]",
        help="Equipment of the customer worked on: installed on an earlier job or recorded by hand.")
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', string="Customer Company")

    @api.depends('fs_picking_ids')
    def _compute_fs_picking_count(self):
        for task in self:
            task.fs_picking_count = len(task.fs_picking_ids)

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        equipment = self.equipment_id
        if equipment:
            self.site_equipment = equipment._fs_text()
            if equipment.partner_id:
                self.site_partner_id = equipment.partner_id

    def action_view_fs_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('fs_task_id', '=', self.id)]
        action['context'] = {'create': False}
        if len(self.fs_picking_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.fs_picking_ids.id
        return action

    # ------------------------------------------------------------------
    # Parts
    # ------------------------------------------------------------------

    def _fs_default_part_location(self):
        """ Where parts are taken from: the van of the technician using the screen, the van of a
        technician of the job, or the stock of the warehouse. """
        technicians = self.sudo().technician_ids
        mine = technicians.filtered(lambda e: e.user_id == self.env.user)
        van = (mine or technicians).filtered('van_location_id')[:1].van_location_id
        if van:
            return van
        company = self._fs_company() if self else self.env.company
        return self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', company.id)], limit=1).lot_stock_id

    def _fs_on_done(self):
        res = super()._fs_on_done()
        self._fs_create_part_moves()
        return res

    def _fs_part_destination(self):
        self.ensure_one()
        partner = self.site_partner_id or self.partner_id
        return partner.property_stock_customer or self.env.ref('stock.stock_location_customers')

    def _fs_part_move_values(self, part, picking):
        """ Values of the stock move of a part. Override to link it to other documents. """
        return {
            'product_id': part.product_id.id,
            'product_uom_qty': part.quantity,
            'uom_id': part.product_uom_id.id,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id,
            'picking_id': picking.id,
            'company_id': picking.company_id.id,
            'partner_id': picking.partner_id.id,
            'origin': picking.origin,
        }

    def _fs_create_part_moves(self):
        """ Take the parts of the jobs out of their location: one validated transfer per job and
        location, to the customer. The serial numbers installed are recorded on the site. """
        Picking = self.env['stock.picking'].sudo()
        for job in self.sudo():
            parts = job.part_ids.filtered(lambda p: p.state == 'draft' and p.product_id.type == 'consu')
            if not parts:
                continue
            destination = job._fs_part_destination()
            for location, location_parts in parts.grouped('location_id').items():
                warehouse = location.warehouse_id
                picking_type = warehouse.out_type_id or self.env['stock.picking.type'].sudo().search([
                    ('code', '=', 'outgoing'), ('company_id', '=', location.company_id.id)], limit=1)
                picking = Picking.create({
                    'picking_type_id': picking_type.id,
                    'location_id': location.id,
                    'location_dest_id': destination.id,
                    'partner_id': (job.site_partner_id or job.partner_id).id,
                    'origin': job.job_number or job.name,
                    'fs_task_id': job.id,
                    'company_id': location.company_id.id or job._fs_company().id,
                })
                moves = self.env['stock.move'].sudo()
                for part in location_parts:
                    move = moves.create(job._fs_part_move_values(part, picking))
                    part.move_id = move
                    moves |= move
                picking.action_confirm()
                for part in location_parts:
                    move = part.move_id
                    move.move_line_ids.unlink()
                    self.env['stock.move.line'].sudo().create({
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': part.product_id.id,
                        'uom_id': part.product_uom_id.id,
                        'quantity': part.quantity,
                        'lot_id': part.lot_id.id,
                        'location_id': location.id,
                        'location_dest_id': destination.id,
                    })
                    move.picked = True
                picking._action_done()
                location_parts.write({'state': 'done'})
            job._fs_record_equipment(parts)

    def _fs_record_equipment(self, parts):
        self.ensure_one()
        Equipment = self.env['om.fs.equipment'].sudo()
        site = self.site_partner_id or self.partner_id
        for part in parts.filtered(lambda p: p.install_on_site and p.lot_id):
            if Equipment.search_count([('lot_id', '=', part.lot_id.id), ('partner_id', '=', site.id)]):
                continue
            equipment = Equipment.create({
                'partner_id': site.id,
                'product_id': part.product_id.id,
                'lot_id': part.lot_id.id,
                'installed_on': fields.Date.context_today(self),
                'install_task_id': self.id,
                'company_id': self._fs_company().id,
            })
            if not self.equipment_id:
                self.equipment_id = equipment

    # ------------------------------------------------------------------
    # Technician screen
    # ------------------------------------------------------------------

    def _fs_mobile_data(self):
        data = super()._fs_mobile_data()
        location = self._fs_default_part_location()
        data['extra'].update({
            'stock': True,
            'parts': self.sudo().part_ids._fs_mobile_data(),
            'part_location': location.display_name,
        })
        return data

    def fs_mobile_part_products(self, query=''):
        """ Products to pick from: those in stock in the location of the parts first. """
        self.ensure_one()
        location = self._fs_default_part_location()
        Product = self.env['product.product'].sudo()
        domain = [('type', '=', 'consu')]
        if query:
            domain += ['|', '|', ('name', 'ilike', query), ('default_code', 'ilike', query),
                       ('barcode', '=', query)]
        products = Product.search(domain, limit=40)
        quantities = {}
        if location:
            for quant in self.env['stock.quant'].sudo().search([
                    ('location_id', 'child_of', location.id), ('product_id', 'in', products.ids)]):
                quantities[quant.product_id.id] = quantities.get(quant.product_id.id, 0.0) + quant.quantity
        result = [{
            'id': product.id,
            'name': product.display_name,
            'tracking': product.tracking,
            'uom': product.uom_id.name,
            'available': quantities.get(product.id, 0.0),
        } for product in products]
        result.sort(key=lambda p: (p['available'] <= 0, p['name']))
        return result[:20]

    def fs_mobile_part_lots(self, product_id):
        """ Lots and serial numbers of the product in stock in the location of the parts. """
        self.ensure_one()
        location = self._fs_default_part_location()
        quants = self.env['stock.quant'].sudo().search([
            ('location_id', 'child_of', location.id),
            ('product_id', '=', product_id),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
        ])
        used = self.sudo().part_ids.lot_id
        lots = quants.lot_id - used if self.env['product.product'].browse(product_id).tracking == 'serial' \
            else quants.lot_id
        return [{'id': lot.id, 'name': lot.name} for lot in lots]

    def fs_mobile_add_part(self, product_id, quantity=1.0, lot_id=False):
        self.ensure_one()
        self._fs_check_open()
        product = self.env['product.product'].sudo().browse(product_id).exists()
        if not product:
            raise UserError(self.env._("Choose a product."))
        if product.tracking and not lot_id:
            raise UserError(self.env._("Choose the lot or serial number of %s.", product.display_name))
        if product.tracking == 'serial':
            quantity = 1.0
        self.sudo().part_ids = [Command.create({
            'product_id': product.id,
            'quantity': quantity or 1.0,
            'product_uom_id': product.uom_id.id,
            'lot_id': lot_id or False,
            'location_id': self._fs_default_part_location().id,
        })]
        return self._fs_mobile_data()

    def fs_mobile_remove_part(self, part_id):
        self.ensure_one()
        self._fs_check_open()
        self.sudo().part_ids.filtered(lambda p: p.id == part_id and p.state == 'draft').unlink()
        return self._fs_mobile_data()

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------

    @api.model
    def _fs_stock_demo(self):
        """ Demo data: vans for the demo technicians, stocked with parts and serial numbers. """
        Quant = self.env['stock.quant'].sudo()
        stock = [
            ('om_field_service_stock.product_fs_gasket_kit', False, 6),
            ('om_field_service_stock.product_fs_valve', False, 4),
            ('om_field_service_stock.product_fs_thermostat', 'om_field_service_stock.lot_fs_thermostat_1', 1),
            ('om_field_service_stock.product_fs_thermostat', 'om_field_service_stock.lot_fs_thermostat_2', 1),
        ]
        for xmlid in ('hr.employee_qdp', 'hr.employee_al'):
            employee = self.env.ref(xmlid, raise_if_not_found=False)
            if not employee or employee.van_location_id:
                continue
            employee.action_create_van_location()
            for product_xmlid, lot_xmlid, quantity in stock:
                product = self.env.ref(product_xmlid, raise_if_not_found=False)
                lot = self.env.ref(lot_xmlid, raise_if_not_found=False) if lot_xmlid else self.env['stock.lot']
                if not product or (lot and Quant.search_count([('lot_id', '=', lot.id), ('quantity', '>', 0)])):
                    continue
                Quant._update_available_quantity(product, employee.van_location_id, quantity, lot_id=lot or None)
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        lot = self.env.ref('om_field_service_stock.lot_fs_thermostat_3', raise_if_not_found=False)
        if warehouse and lot and not Quant.search_count([('lot_id', '=', lot.id)]):
            Quant._update_available_quantity(lot.product_id, warehouse.lot_stock_id, 1, lot_id=lot)
