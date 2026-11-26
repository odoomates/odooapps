import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import float_round


class OmStockBarcode(models.AbstractModel):
    """The server side of the Barcode app: compact data for each screen and
    one method per scan that checks it and applies it. Everything runs with
    the rights of the user."""

    _name = 'om.stock.barcode'
    _description = "Barcode App"

    # ------------------------------------------------------------------
    # Barcode resolution
    # ------------------------------------------------------------------

    @api.model
    def _company_domain(self, field='company_id'):
        return Domain(field, 'in', self.env.companies.ids + [False])

    @api.model
    def _gs1_nomenclature(self):
        nomenclature = self.env.company.nomenclature_id
        if nomenclature.is_gs1_nomenclature:
            return nomenclature
        return self.env.ref('barcodes_gs1_nomenclature.default_gs1_nomenclature', raise_if_not_found=False)

    @api.model
    def _find_product(self, code):
        """Product and quantity (in the product unit) for a product or packaging barcode."""
        Product = self.env['product.product'].with_context(skip_preprocess_gs1=True, active_test=True)
        product = Product.search(Domain('barcode', '=', code) & self._company_domain(), limit=1)
        if product:
            return product, 1.0
        packaging = self.env['product.uom'].with_context(skip_preprocess_gs1=True).search(
            Domain('barcode', '=', code) & self._company_domain(), limit=1)
        if packaging and packaging.product_id.active:
            product = packaging.product_id
            return product, packaging.uom_id._compute_quantity(1.0, product.uom_id)
        return Product, 0.0

    @api.model
    def _find_product_gtin(self, gtin):
        """A GS1 GTIN is 14 digits; the product may carry it as EAN-13, UPC-A or EAN-8."""
        candidates = [gtin]
        stripped = gtin.lstrip('0')
        for length in (13, 12, 8):
            if len(stripped) <= length:
                candidates.append(stripped.rjust(length, '0'))
        Product = self.env['product.product'].with_context(skip_preprocess_gs1=True)
        product = Product.search(Domain('barcode', 'in', candidates) & self._company_domain(), limit=1)
        if product:
            return product, 1.0
        packaging = self.env['product.uom'].with_context(skip_preprocess_gs1=True).search(
            Domain('barcode', 'in', candidates) & self._company_domain(), limit=1)
        if packaging:
            return packaging.product_id, packaging.uom_id._compute_quantity(1.0, packaging.product_id.uom_id)
        return Product, 0.0

    @api.model
    def _parse_gs1(self, barcode):
        nomenclature = self._gs1_nomenclature()
        if not nomenclature or len(barcode) < 4:
            return None
        try:
            parts = nomenclature.gs1_decompose_extended(barcode)
        except (ValidationError, UserError, ValueError):
            return None
        if not parts:
            return None
        result = {'gs1': True}
        for part in parts:
            kind, value = part['type'], part['value']
            if kind == 'product':
                result['product'], result['qty'] = self._find_product_gtin(str(value))
                if not result['product']:
                    result['unknown_gtin'] = str(value)
            elif kind == 'lot':
                result['lot_name'] = value
            elif kind == 'quantity':
                result['gs1_qty'] = float(value)
            elif kind in ('expiration_date', 'use_date'):
                result.setdefault('expiry', value)
            elif kind in ('location', 'location_dest'):
                location = self.env['stock.location'].search(
                    Domain('barcode', '=', str(value)) & self._company_domain(), limit=1)
                if location:
                    result['location'] = location
            elif kind == 'package':
                package = self.env['stock.package'].search(
                    Domain('name', '=', str(value)) & self._company_domain(), limit=1)
                result['package'] = package
                if not package:
                    result['new_package_name'] = str(value)
        return result

    @api.model
    def _resolve(self, barcode, products=None):
        """What a barcode is. Returns a dict with any of: picking_type, picking,
        location, package, product (with qty in its unit), lots, lot_name,
        expiry, gs1. ``products`` narrows the lots to those of a transfer."""
        barcode = (barcode or '').strip()
        res = {'barcode': barcode}
        if not barcode:
            return res
        picking_type = self.env['stock.picking.type'].search(
            Domain('barcode', '=', barcode) & Domain('company_id', 'in', self.env.companies.ids), limit=1)
        if picking_type:
            res['picking_type'] = picking_type
            return res
        Location = self.env['stock.location']
        location = Location.search(Domain('barcode', '=', barcode) & self._company_domain(), limit=1)
        if not location and '/' in barcode:
            location = Location.search(Domain('complete_name', '=', barcode) & self._company_domain(), limit=1)
        if location:
            res['location'] = location
            return res
        product, qty = self._find_product(barcode)
        if product:
            res.update(product=product, qty=qty)
            return res
        package = self.env['stock.package'].search(Domain('name', '=', barcode) & self._company_domain(), limit=1)
        if package:
            res['package'] = package
            return res
        lot_domain = Domain('name', '=', barcode) & self._company_domain()
        if products:
            lot_domain &= Domain('product_id', 'in', products.ids)
        lots = self.env['stock.lot'].search(lot_domain, limit=20)
        if lots:
            res['lots'] = lots
            res['lot_name'] = barcode
            return res
        picking = self.env['stock.picking'].search(
            Domain('name', '=', barcode) & Domain('company_id', 'in', self.env.companies.ids), limit=1)
        if picking:
            res['picking'] = picking
            return res
        gs1 = self._parse_gs1(barcode)
        if gs1 and (gs1.get('product') or gs1.get('location') or gs1.get('package') or gs1.get('lot_name')):
            if 'gs1_qty' in gs1 and gs1.get('product'):
                gs1['qty'] = gs1['gs1_qty'] * (gs1.get('qty') or 1.0)
            res.update(gs1)
            if res.get('lot_name') and not res.get('product'):
                lot_domain = Domain('name', '=', res['lot_name']) & self._company_domain()
                if products:
                    lot_domain &= Domain('product_id', 'in', products.ids)
                res['lots'] = self.env['stock.lot'].search(lot_domain, limit=20)
            return res
        nomenclature = self.env.company.nomenclature_id
        if nomenclature and not nomenclature.is_gs1_nomenclature:
            parsed = nomenclature.parse_barcode(barcode)
            if isinstance(parsed, dict) and parsed.get('type') in ('product', 'weight') and parsed.get('base_code') != barcode:
                product, qty = self._find_product(parsed['base_code'])
                if product:
                    if parsed['type'] == 'weight' and parsed.get('value'):
                        qty = float(parsed['value'])
                    res.update(product=product, qty=qty)
                    return res
        product = self.env['product.product'].search(
            Domain('default_code', '=', barcode) & self._company_domain(), limit=1)
        if product:
            res.update(product=product, qty=1.0)
        return res

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @api.model
    def _settings(self):
        company = self.env.company
        return {
            'sound': company.om_barcode_sound,
            'camera': company.om_barcode_camera,
            'multi_location': self.env.user.has_group('stock.group_stock_multi_locations'),
            'lots': self.env.user.has_group('stock.group_production_lot'),
            'packages': self.env.user.has_group('stock.group_tracking_lot'),
            'is_manager': self.env.user.has_group('stock.group_stock_manager'),
        }

    @api.model
    def _product_data(self, product):
        return {
            'id': product.id,
            'name': product.display_name,
            'code': product.default_code or '',
            'barcode': product.barcode or '',
            'tracking': product.tracking or 'none',
            'uom': product.uom_id.name,
        }

    @api.model
    def _loc(self, location):
        return {'id': location.id, 'name': location.complete_name} if location else False

    @api.model
    def _qty(self, qty, uom):
        return uom[:1].round(qty or 0.0) if uom else float_round(qty or 0.0, precision_digits=3)

    @api.model
    def _fmt(self, qty):
        return ('%.3f' % (qty or 0.0)).rstrip('0').rstrip('.')

    @api.model
    def _feedback(self, kind, message, **values):
        values.update(type=kind, message=message)
        return values

    # ------------------------------------------------------------------
    # Home screen and transfer lists
    # ------------------------------------------------------------------

    @api.model
    def get_home(self):
        types = self.env['stock.picking.type'].search(
            Domain('code', 'in', ['incoming', 'outgoing', 'internal'])
            & Domain('company_id', 'in', self.env.companies.ids),
            order='sequence, id')
        data = []
        for picking_type in types:
            data.append({
                'id': picking_type.id,
                'name': picking_type.name,
                'code': picking_type.code,
                'warehouse': picking_type.warehouse_id.name or '',
                'ready': picking_type.count_picking_ready,
                'waiting': picking_type.count_picking_waiting,
                'late': picking_type.count_picking_late,
            })
        return {
            'operation_types': data,
            'settings': self._settings(),
            'company': self.env.company.name,
        }

    @api.model
    def _picking_list_data(self, pickings):
        return [{
            'id': picking.id,
            'name': picking.name,
            'partner': picking.partner_id.display_name or '',
            'origin': picking.origin or '',
            'date': fields.Datetime.to_string(picking.scheduled_date) if picking.scheduled_date else '',
            'state': picking.state,
            'state_label': dict(picking._fields['state']._description_selection(self.env)).get(picking.state),
            'late': bool(picking.scheduled_date and picking.scheduled_date < fields.Datetime.now()
                         and picking.state in ('assigned', 'confirmed', 'waiting')),
            'type': picking.picking_type_id.name,
            'products': len(picking.move_ids),
        } for picking in pickings]

    @api.model
    def get_pickings(self, picking_type_id=False, search=''):
        domain = Domain('state', 'in', ['draft', 'confirmed', 'waiting', 'assigned']) & Domain(
            'company_id', 'in', self.env.companies.ids)
        if picking_type_id:
            domain &= Domain('picking_type_id', '=', picking_type_id)
        else:
            domain &= Domain('picking_type_id.code', 'in', ['incoming', 'outgoing', 'internal'])
        if search:
            domain &= (Domain('name', 'ilike', search) | Domain('origin', 'ilike', search)
                       | Domain('partner_id', 'ilike', search) | Domain('product_id', 'ilike', search))
        pickings = self.env['stock.picking'].search(domain, order='priority desc, scheduled_date, id', limit=80)
        picking_type = self.env['stock.picking.type'].browse(picking_type_id) if picking_type_id else False
        return {
            'picking_type': {
                'id': picking_type.id, 'name': picking_type.display_name, 'code': picking_type.code,
            } if picking_type else False,
            'pickings': self._picking_list_data(pickings),
        }

    @api.model
    def home_scan(self, barcode):
        """A scan on the home screen or in a transfer list: an operation type or
        a transfer opens it, anything else is looked up."""
        res = self._resolve(barcode)
        if res.get('picking_type'):
            return {'open': 'type', 'id': res['picking_type'].id}
        if res.get('picking'):
            picking = res['picking']
            if picking.state in ('done', 'cancel'):
                return self._feedback('error', self.env._("%s is already done or cancelled.", picking.name))
            return {'open': 'picking', 'id': picking.id}
        if len(res) > 1:
            return {'open': 'lookup', 'barcode': barcode}
        return self._feedback('error', self.env._("Unknown barcode: %s", barcode))

    @api.model
    def new_picking(self, picking_type_id):
        picking_type = self.env['stock.picking.type'].browse(picking_type_id)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
        })
        return {'open': 'picking', 'id': picking.id}

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @api.model
    def _quant_rows(self, quants):
        return [{
            'id': quant.id,
            'product': quant.product_id.display_name,
            'product_id': quant.product_id.id,
            'location': quant.location_id.complete_name,
            'lot': quant.lot_id.name or '',
            'package': quant.package_id.name or '',
            'quantity': self._qty(quant.quantity, quant.uom_id),
            'reserved': self._qty(quant.reserved_quantity, quant.uom_id),
            'uom': quant.uom_id.name,
        } for quant in quants]

    @api.model
    def _internal_quants(self, domain, limit=200):
        domain = Domain(domain) & Domain('location_id.usage', 'in', ['internal', 'transit']) & Domain(
            'quantity', '!=', 0) & Domain('company_id', 'in', self.env.companies.ids)
        return self.env['stock.quant'].search(domain, order='location_id, product_id, lot_id', limit=limit)

    @api.model
    def lookup(self, barcode):
        res = self._resolve(barcode)
        if res.get('product'):
            product = res['product']
            quants = self._internal_quants(Domain('product_id', '=', product.id))
            if res.get('lot_name'):
                quants = quants.filtered(lambda q: q.lot_id.name == res['lot_name'])
            return {
                'kind': 'product',
                'title': product.display_name,
                'product': dict(self._product_data(product),
                                on_hand=self._qty(product.qty_available, product.uom_id),
                                forecast=self._qty(product.virtual_available, product.uom_id),
                                incoming=self._qty(product.incoming_qty, product.uom_id),
                                outgoing=self._qty(product.outgoing_qty, product.uom_id)),
                'quants': self._quant_rows(quants),
            }
        if res.get('lots'):
            lot = res['lots'][:1]
            quants = self._internal_quants(Domain('lot_id', '=', lot.id))
            move_lines = self.env['stock.move.line'].search(
                Domain('lot_id', '=', lot.id) & Domain('state', '=', 'done'), order='date desc, id desc', limit=15)
            expiry = lot['expiration_date'] if 'expiration_date' in lot._fields else False
            return {
                'kind': 'lot',
                'title': lot.name,
                'product': self._product_data(lot.product_id),
                'lot': {
                    'name': lot.name,
                    'expiry': fields.Datetime.to_string(expiry) if expiry else '',
                    'quantity': self._qty(lot.product_qty, lot.product_id.uom_id),
                    'others': len(res['lots']) - 1,
                },
                'quants': self._quant_rows(quants),
                'history': [{
                    'date': fields.Datetime.to_string(ml.date),
                    'reference': ml.reference or '',
                    'from': ml.location_id.complete_name,
                    'to': ml.location_dest_id.complete_name,
                    'quantity': self._qty(ml.quantity, ml.uom_id),
                    'uom': ml.uom_id.name,
                } for ml in move_lines if not ml.uom_id.is_zero(ml.quantity)],
            }
        if res.get('location'):
            location = res['location']
            quants = self._internal_quants(Domain('location_id', 'child_of', location.id))
            return {
                'kind': 'location',
                'title': location.complete_name,
                'location': {'id': location.id, 'name': location.complete_name, 'usage': location.usage},
                'quants': self._quant_rows(quants),
            }
        if res.get('package'):
            package = res['package']
            return {
                'kind': 'package',
                'title': package.name,
                'package': {
                    'name': package.name,
                    'location': package.location_id.complete_name or '',
                    'type': package.package_type_id.name or '',
                },
                'quants': self._quant_rows(package.contained_quant_ids),
            }
        if res.get('picking'):
            picking = res['picking']
            return {'kind': 'picking', 'title': picking.name, 'pickings': self._picking_list_data(picking)}
        if res.get('picking_type'):
            return {'kind': 'type', 'title': res['picking_type'].display_name, 'id': res['picking_type'].id}
        return self._feedback('error', self.env._("Unknown barcode: %s", barcode))

    @api.model
    def search_products(self, search, limit=20):
        """Manual fallback: products by name, internal reference or barcode."""
        if not search:
            return []
        products = self.env['product.product'].search(
            (Domain('name', 'ilike', search) | Domain('default_code', 'ilike', search)
             | Domain('barcode', 'ilike', search)) & Domain('type', '=', 'consu') & self._company_domain(),
            limit=limit)
        return [self._product_data(product) for product in products]

    @api.model
    def _clean_lot_name(self, value):
        return re.sub(r'\s+', ' ', value or '').strip()
