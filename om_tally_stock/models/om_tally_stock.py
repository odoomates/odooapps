from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

ACTIONS = [('link', 'Link'), ('create', 'Create'), ('skip', 'Skip')]
# usual names of the units of Tally -> name of the unit in Odoo
UNIT_NAMES = {
    'nos': 'Units', 'no': 'Units', 'pcs': 'Units', 'pc': 'Units', 'pieces': 'Units', 'numbers': 'Units',
    'unt': 'Units', 'units': 'Units', 'kg': 'kg', 'kgs': 'kg', 'kilograms': 'kg', 'g': 'g', 'gms': 'g',
    'grams': 'g', 'ltr': 'L', 'ltrs': 'L', 'litre': 'L', 'liters': 'L', 'l': 'L', 'ml': 'ml', 'mtr': 'm',
    'mtrs': 'm', 'meter': 'm', 'metre': 'm', 'm': 'm', 'mm': 'mm', 'ton': 't', 'tonne': 't', 'mt': 't',
    'sqm': 'm²', 'hrs': 'Hours', 'hours': 'Hours', 'days': 'Days',
}


def _norm(text):
    return ''.join(char for char in (text or '').lower() if char.isalnum())


class OmTallyUnit(models.Model):
    _inherit = 'om.tally.unit'

    uom_action = fields.Selection(ACTIONS, string='Unit Action', default='create')
    uom_id = fields.Many2one('uom.uom', string='Odoo Unit', ondelete='set null')


class OmTallyStockGroup(models.Model):
    _inherit = 'om.tally.stock.group'

    categ_action = fields.Selection(ACTIONS, string='Category Action', default='create')
    categ_id = fields.Many2one('product.category', string='Product Category', ondelete='set null')


class OmTallyStockCategory(models.Model):
    _inherit = 'om.tally.stock.category'

    categ_action = fields.Selection(ACTIONS, string='Category Action', default='create')
    categ_id = fields.Many2one('product.category', string='Product Category', ondelete='set null')
    tag_id = fields.Many2one('product.tag', string='Product Tag', ondelete='set null')


class OmTallyGodown(models.Model):
    _inherit = 'om.tally.godown'

    location_action = fields.Selection(ACTIONS, string='Location Action', default='create')
    location_id = fields.Many2one('stock.location', string='Odoo Location', ondelete='set null',
                                  domain="[('usage', '=', 'internal'), ('company_id', 'in', (False, company_id))]")


class OmTallyStockItem(models.Model):
    _inherit = 'om.tally.stock.item'

    product_action = fields.Selection(ACTIONS, string='Product Action', default='create',
                                      help="Link: use the Odoo product. Create: make a product from the stock item. "
                                           "Skip: the invoice lines keep the name of the item, without product.")
    product_id = fields.Many2one('product.product', string='Odoo Product', ondelete='set null')
    product_match_note = fields.Char(string='Product Matched By', readonly=True)


class OmTallyImport(models.Model):
    _inherit = 'om.tally.import'

    stock_item_ids = fields.One2many('om.tally.stock.item', 'import_id', string='Stock Items')
    unit_ids = fields.One2many('om.tally.unit', 'import_id', string='Units')
    godown_ids = fields.One2many('om.tally.godown', 'import_id', string='Godowns')
    stock_group_ids = fields.One2many('om.tally.stock.group', 'import_id', string='Stock Groups')
    stock_category_ids = fields.One2many('om.tally.stock.category', 'import_id', string='Stock Categories')
    stock_opening = fields.Boolean(string='Import the Opening Stock', default=True,
                                   help="Set the quantities of the stock items per godown and batch on the cut-over "
                                        "date, valued at the rate of Tally.")
    stock_warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse',
                                         domain="[('company_id', '=', company_id)]",
                                         help="The godowns of Tally become locations of this warehouse.")
    stock_category_source = fields.Selection([
        ('group', 'Stock Groups'),
        ('category', 'Stock Categories'),
    ], string='Product Categories From', default='group', required=True,
        help="The classification of Tally that gives the product category; the other one gives product tags.")
    stock_opening_done = fields.Boolean(readonly=True, copy=False)

    # proposing

    def _om_tally_propose_mapping(self):
        res = super()._om_tally_propose_mapping()
        self._om_tally_propose_stock()
        return res

    def _om_tally_propose_stock(self):
        env, company = self.env, self.company_id
        Mapping = env['om.tally.mapping']
        if not self.stock_warehouse_id:
            self.stock_warehouse_id = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        uoms = env['uom.uom'].search([])
        uom_by_name = {_norm(uom.name): uom for uom in uoms}
        for unit in self.unit_ids:
            uom = Mapping._om_tally_find(company, 'unit', unit.guid, 'uom.uom')
            if not uom:
                for name in (unit.name, unit.formal_name, (unit.uqc or '').split('-')[-1]):
                    uom = uom_by_name.get(_norm(UNIT_NAMES.get((name or '').strip().lower(), name)))
                    if uom:
                        break
            unit.write({'uom_id': uom.id if uom else False, 'uom_action': 'link' if uom else 'create'})
        Category = env['product.category']
        for record in list(self.stock_group_ids) + list(self.stock_category_ids):
            tally_type = 'stock_group' if record._name == 'om.tally.stock.group' else 'stock_category'
            category = Mapping._om_tally_find(company, tally_type, record.guid, 'product.category') or \
                Category.search([('name', '=ilike', record.name)], limit=1)
            record.write({'categ_id': category.id, 'categ_action': 'link' if category else 'create'})
        main = self.stock_warehouse_id.lot_stock_id
        for godown in self.godown_ids:
            location = Mapping._om_tally_find(company, 'godown', godown.guid, 'stock.location')
            if not location and (godown.reserved_name == 'Main Location' or godown.name == 'Main Location'):
                location = main
            if not location:
                location = env['stock.location'].search([
                    ('name', '=ilike', godown.name), ('usage', '=', 'internal'),
                    ('company_id', 'in', (False, company.id))], limit=1)
            godown.write({'location_id': location.id, 'location_action': 'link' if location else 'create'})
        Product = env['product.product'].with_context(active_test=False)
        company_domain = [('company_id', 'in', (False, company.id))]
        has_hsn = 'l10n_in_hsn_code' in Product._fields and self.tally_country == 'in'
        for item in self.stock_item_ids.filtered(lambda i: not (i.product_id and i.product_action == 'link')):
            product = Mapping._om_tally_find(company, 'stock_item', item.guid, 'product.product')
            note = product and env._("Imported before")
            if not product and item.part_number:
                product = Product.search(company_domain + [('default_code', '=ilike', item.part_number)], limit=1)
                note = product and env._("Part number")
            if not product:
                product = Product.search(company_domain + [('name', '=ilike', item.name)], limit=1)
                note = product and env._("Name")
            if not product and has_hsn and item.hsn_code:
                same_hsn = Product.search(company_domain + [('l10n_in_hsn_code', '=', item.hsn_code)], limit=2)
                product = same_hsn if len(same_hsn) == 1 else Product
                note = product and env._("HSN/SAC")
            item.write({'product_id': product.id, 'product_action': 'link' if product else 'create',
                        'product_match_note': note or False})

    # creating and linking

    def _om_tally_apply_masters(self):
        res = super()._om_tally_apply_masters()
        self._om_tally_apply_stock()
        return res

    def _om_tally_item_taxes(self, item, use):
        """ The tax of Odoo at the GST rate of the item (India), for sales or purchases. """
        if not item.gst_rate or self.tally_country != 'in':
            return self.env['account.tax']
        taxes = self.env['account.tax'].search([
            ('company_id', '=', self.company_id.id), ('type_tax_use', '=', use), ('amount', '=', item.gst_rate),
            ('amount_type', 'in', ('group', 'percent'))])
        group = taxes.filtered(lambda t: t.amount_type == 'group' and 'GST' in (t.name or '').upper()
                               and 'RC' not in (t.name or '').upper())
        return group[:1] or taxes.filtered(lambda t: len(taxes) == 1)

    def _om_tally_apply_stock(self):
        env, company = self.env, self.company_id
        Mapping = env['om.tally.mapping']
        errors = []
        for unit in self.unit_ids:
            if unit.uom_action == 'create' and not unit.uom_id:
                unit.uom_id = Mapping._om_tally_find(company, 'unit', unit.guid, 'uom.uom') or \
                    env['uom.uom'].create({'name': unit.name})
            elif unit.uom_action == 'link' and not unit.uom_id:
                errors.append(env._("Unit %s: choose the unit to link.", unit.name))
            if unit.uom_id:
                Mapping._om_tally_set(self, 'unit', unit.guid or unit.name, unit.uom_id, unit.name, unit.alter_id)
        source = self.stock_group_ids if self.stock_category_source == 'group' else self.stock_category_ids
        tally_type = 'stock_group' if self.stock_category_source == 'group' else 'stock_category'
        for record in source.sorted(lambda r: len(r.parent_id) and 1 or 0):
            if record.categ_action == 'create' and not record.categ_id:
                record.categ_id = Mapping._om_tally_find(company, tally_type, record.guid, 'product.category') or \
                    env['product.category'].create({'name': record.name, 'parent_id': record.parent_id.categ_id.id})
            if record.categ_id:
                Mapping._om_tally_set(self, tally_type, record.guid or record.name, record.categ_id, record.name)
        tags = self.stock_category_ids if self.stock_category_source == 'group' else self.stock_group_ids
        Tag = env['product.tag']
        tag_by_name = {}
        for record in tags:
            tag_by_name[record.name] = Tag.search([('name', '=ilike', record.name)], limit=1) or \
                Tag.create({'name': record.name})
        warehouse = self.stock_warehouse_id or env['stock.warehouse'].search([('company_id', '=', company.id)],
                                                                             limit=1)
        for godown in self.godown_ids:
            if godown.location_action == 'create' and not godown.location_id:
                godown.location_id = Mapping._om_tally_find(company, 'godown', godown.guid, 'stock.location') or \
                    env['stock.location'].create({
                        'name': godown.name, 'usage': 'internal', 'company_id': company.id,
                        'location_id': (godown.parent_id.location_id or warehouse.view_location_id).id})
            elif godown.location_action == 'link' and not godown.location_id:
                errors.append(env._("Godown %s: choose the location to link.", godown.name))
            if godown.location_id:
                Mapping._om_tally_set(self, 'godown', godown.guid or godown.name, godown.location_id, godown.name)
        Product = env['product.product'].with_company(company)
        has_hsn = 'l10n_in_hsn_code' in Product._fields and self.tally_country == 'in'
        for item in self.stock_item_ids:
            if item.product_action == 'link' and not item.product_id:
                errors.append(env._("Stock item %s: choose the product to link.", item.name))
                continue
            if item.product_action == 'create' and not item.product_id:
                product = Mapping._om_tally_find(company, 'stock_item', item.guid, 'product.product')
                if not product:
                    group = item.stock_group_id if self.stock_category_source == 'group' else item.stock_category_id
                    tag = tag_by_name.get(item.category_name if self.stock_category_source == 'group'
                                          else item.parent_name)
                    batches = {opening.batch_name for opening in item.opening_ids} - {'', 'Primary Batch', False}
                    vals = {
                        'name': item.name,
                        'company_id': company.id,
                        'default_code': item.part_number or False,
                        'type': 'consu',
                        'is_storable': True,
                        'uom_id': item.unit_id.uom_id.id or env.ref('uom.product_uom_unit').id,
                        'categ_id': group.categ_id.id or env.ref('product.product_category_goods').id,
                        'standard_price': item.opening_rate or (
                            item.opening_value / item.opening_quantity if item.opening_quantity else 0.0),
                        'tracking': 'lot' if item.is_batchwise or batches else False,
                        'description': item.description or False,
                        'product_tag_ids': [Command.set(tag.ids)] if tag else False,
                        'taxes_id': [Command.set(self._om_tally_item_taxes(item, 'sale').ids)],
                        'supplier_taxes_id': [Command.set(self._om_tally_item_taxes(item, 'purchase').ids)],
                    }
                    if has_hsn and item.hsn_code:
                        vals['l10n_in_hsn_code'] = item.hsn_code
                    product = Product.create({key: value for key, value in vals.items() if value is not False})
                item.write({'product_id': product.id, 'product_action': 'link',
                            'product_match_note': env._("Created")})
            if item.product_id:
                Mapping._om_tally_set(self, 'stock_item', item.guid or item.name, item.product_id, item.name,
                                      item.alter_id)
        if errors:
            raise UserError("\n".join(errors[:30]))

    def _om_tally_inventory_line_vals(self, inventory_line):
        vals = super()._om_tally_inventory_line_vals(inventory_line)
        product = inventory_line.item_id.product_id
        if product:
            vals['product_id'] = product.id
            uom = self.unit_ids.filtered(lambda u: u.name == inventory_line.unit_name).uom_id
            vals['product_uom_id'] = (uom or product.uom_id).id
        return vals

    # opening stock

    def action_post(self):
        res = super().action_post()
        for record in self.filtered(lambda r: r.stock_opening and not r.stock_opening_done):
            record._om_tally_post_opening_stock()
        return res

    def _om_tally_opening_stock_rows(self):
        """ (item, location, lot name, quantity) of the stock on the cut-over date. Later vouchers are left out:
        the opening stock is the one of Tally's books beginning date when the cut-over is that date. """
        rows = []
        for item in self.stock_item_ids.filtered(lambda i: i.product_id and i.product_action != 'skip'):
            openings = item.opening_ids or [False]
            for opening in openings:
                quantity = opening.quantity if opening else item.opening_quantity
                if not quantity:
                    continue
                location = (opening and opening.godown_id.location_id) or self.stock_warehouse_id.lot_stock_id
                lot_name = opening and opening.batch_name not in ('', 'Primary Batch') and opening.batch_name
                rows.append((item, location, lot_name or False, quantity))
        return rows

    def _om_tally_post_opening_stock(self):
        self.ensure_one()
        env = self.env
        Mapping = env['om.tally.mapping']
        key = f'opening_stock|{self.tally_company_guid or self.tally_company_name}|{self.cutover_date}'
        if Mapping._om_tally_find(self.company_id, 'opening_stock', key, 'res.company'):
            self.stock_opening_done = True
            return
        Quant = env['stock.quant'].with_company(self.company_id).with_context(inventory_mode=True)
        quants = Quant
        for item, location, lot_name, quantity in self._om_tally_opening_stock_rows():
            product = item.product_id
            if item.opening_quantity and item.opening_value and product.cost_method != 'fifo':
                product.with_company(self.company_id).standard_price = item.opening_value / item.opening_quantity
            lot = env['stock.lot']
            if lot_name and product.tracking:
                lot = Mapping._om_tally_find(self.company_id, 'batch', f'{item.guid}|{lot_name}', 'stock.lot') or \
                    env['stock.lot'].search([('product_id', '=', product.id), ('name', '=', lot_name),
                                             ('company_id', 'in', (False, self.company_id.id))], limit=1) or \
                    env['stock.lot'].create({'product_id': product.id, 'name': lot_name,
                                             'company_id': self.company_id.id})
                Mapping._om_tally_set(self, 'batch', f'{item.guid}|{lot_name}', lot, f'{item.name}: {lot_name}')
            quant = Quant.search([('product_id', '=', product.id), ('location_id', '=', location.id),
                                  ('lot_id', '=', lot.id)], limit=1)
            if quant:
                quant.inventory_quantity = quant.quantity + quantity
            else:
                quant = Quant.create({'product_id': product.id, 'location_id': location.id, 'lot_id': lot.id,
                                      'inventory_quantity': quantity})
            quant.accounting_date = self.cutover_date - timedelta(days=1)
            quants |= quant
        if quants:
            quants.with_context(inventory_name=env._("Opening stock from Tally")).action_apply_inventory()
        Mapping._om_tally_set(self, 'opening_stock', key, self.company_id, env._("Opening stock"))
        self.stock_opening_done = True
        self._om_tally_log(env._("Opening stock set for %s lines.", len(quants)), step='post')
