from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class OmStockBarcode(models.AbstractModel):
    _inherit = 'om.stock.barcode'

    # ------------------------------------------------------------------
    # Transfer data
    # ------------------------------------------------------------------

    @api.model
    def _get_picking(self, picking_id):
        picking = self.env['stock.picking'].browse(picking_id).exists()
        if not picking:
            raise UserError(self.env._("This transfer does not exist anymore."))
        picking.check_access('write')
        return picking

    @api.model
    def _line_done(self, line):
        if line.om_barcode_qty or not line.picked:
            return line.om_barcode_qty
        return line.quantity

    @api.model
    def _is_open(self, line):
        """A line still taking scans: not given a destination or a package by a scan."""
        return not line.om_barcode_dest_scanned and not line.om_barcode_packed

    @api.model
    def _scanned_lines(self, picking):
        return picking.move_line_ids.filtered(lambda ml: ml.om_barcode_qty > 0)

    @api.model
    def _pending_dest_lines(self, picking):
        return self._scanned_lines(picking).filtered(lambda ml: not ml.om_barcode_dest_scanned)

    @api.model
    def _pending_pack_lines(self, picking):
        return self._scanned_lines(picking).filtered(
            lambda ml: not ml.om_barcode_packed and not ml.om_barcode_dest_scanned and not ml.result_package_id)

    @api.model
    def _group_location(self, picking, line):
        if picking.picking_type_code == 'incoming':
            return line.location_dest_id
        return line.location_id

    @api.model
    def get_picking(self, picking_id):
        picking = self._get_picking(picking_id)
        picking_type = picking.picking_type_id
        lines = []
        for line in picking.move_line_ids.sorted(lambda ml: (
                self._group_location(picking, ml).complete_name or '', ml.product_id.display_name, ml.id)):
            done = self._line_done(line)
            demand = line.quantity
            lines.append({
                'id': line.id,
                'move_id': line.move_id.id,
                'product': self._product_data(line.product_id),
                'demand': self._qty(demand, line.uom_id),
                'done': self._qty(done, line.uom_id),
                'uom': line.uom_id.name,
                'lot': line.lot_id.name or line.lot_name or '',
                'package': line.package_id.name or '',
                'result_package': line.result_package_id.name or '',
                'location': self._loc(line.location_id),
                'location_dest': self._loc(line.location_dest_id),
                'group': self._loc(self._group_location(picking, line)),
                'dest_scanned': line.om_barcode_dest_scanned,
                'packed': line.om_barcode_packed,
                'complete': bool(done) and line.uom_id.compare(done, demand) >= 0,
                'extra': bool(done) and line.uom_id.compare(done, demand) > 0,
            })
        # The part of each move not reserved yet: shown so it can be scanned.
        missing = []
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            reserved = sum(ml.uom_id._compute_quantity(ml.quantity, move.uom_id) for ml in move.move_line_ids)
            left = move.product_uom_qty - reserved
            if move.uom_id.compare(left, 0) > 0:
                missing.append({
                    'move_id': move.id,
                    'product': self._product_data(move.product_id),
                    'demand': self._qty(left, move.uom_id),
                    'uom': move.uom_id.name,
                })
        demand_total = sum(picking.move_ids.filtered(lambda m: m.state != 'cancel').mapped('product_uom_qty'))
        done_total = sum(self._line_done(line) for line in picking.move_line_ids)
        return {
            'id': picking.id,
            'name': picking.name,
            'state': picking.state,
            'state_label': dict(picking._fields['state']._description_selection(self.env)).get(picking.state),
            'code': picking.picking_type_code,
            'type': {'id': picking_type.id, 'name': picking_type.name},
            'partner': picking.partner_id.display_name or '',
            'origin': picking.origin or '',
            'date': fields.Datetime.to_string(picking.scheduled_date) if picking.scheduled_date else '',
            'location': self._loc(picking.location_id),
            'location_dest': self._loc(picking.location_dest_id),
            'source_internal': picking.location_id.usage in ('internal', 'transit'),
            'dest_internal': picking.location_dest_id.usage in ('internal', 'transit'),
            'rules': {
                'source': picking_type.om_barcode_require_source,
                'dest': picking_type.om_barcode_require_dest,
                'package': picking_type.om_barcode_require_package,
                'unplanned': picking_type.om_barcode_allow_unplanned,
                'lots': picking_type.use_create_lots or picking_type.use_existing_lots,
            },
            'lines': lines,
            'missing': missing,
            'pending_dest': len(self._pending_dest_lines(picking)),
            'pending_pack': len(self._pending_pack_lines(picking)),
            'progress': {'done': done_total, 'demand': demand_total},
            'settings': self._settings(),
        }

    @api.model
    def _answer(self, picking, feedback, state, **extra):
        feedback.update(state=state, picking=self.get_picking(picking.id), **extra)
        return feedback

    # ------------------------------------------------------------------
    # Scans
    # ------------------------------------------------------------------

    @api.model
    def picking_scan(self, picking_id, barcode, state=None):
        picking = self._get_picking(picking_id)
        state = dict(state or {})
        if picking.state in ('done', 'cancel'):
            return self._answer(picking, self._feedback('error', self.env._("This transfer is already done.")), state)
        try:
            with self.env.cr.savepoint():
                feedback = self._picking_scan(picking, barcode, state)
        except UserError as error:
            feedback = self._feedback('error', str(error.args[0]) if error.args else str(error))
        return self._answer(picking, feedback, state)

    @api.model
    def _picking_scan(self, picking, barcode, state):
        res = self._resolve(barcode, products=picking.move_ids.product_id)
        pending = self.env['product.product'].browse(state.get('pending_product_id') or []).exists()
        if res.get('picking_type') or res.get('picking'):
            if res.get('picking') == picking:
                return self._feedback('info', self.env._("You are in %s.", picking.name))
            return self.home_scan(barcode)
        if res.get('location') and not res.get('product'):
            return self._scan_location(picking, res['location'], state)
        if res.get('package') and not res.get('product'):
            return self._scan_package(picking, res['package'], state)
        if res.get('new_package_name') and not res.get('product'):
            package = self.env['stock.package'].create({'name': res['new_package_name']})
            return self._scan_package(picking, package, state)
        if res.get('location'):
            feedback = self._scan_location(picking, res['location'], state)
            if feedback['type'] == 'error':
                return feedback
        if res.get('product'):
            return self._scan_product(
                picking, res['product'], res.get('qty') or 1.0, state,
                lot_name=res.get('lot_name'), expiry=res.get('expiry'))
        if res.get('unknown_gtin'):
            return self._feedback('error', self.env._("No product has the barcode %s.", res['unknown_gtin']))
        if pending:
            # The scan after a tracked product is its lot or serial number.
            return self._scan_product(picking, pending, state.get('pending_qty') or 1.0, state,
                                      lot_name=res.get('lot_name') or barcode, expiry=res.get('expiry'))
        if res.get('lots'):
            products = res['lots'].product_id & picking.move_ids.product_id
            if len(products) == 1:
                return self._scan_product(picking, products, 1.0, state, lot_name=res['lot_name'])
            if len(res['lots'].product_id) == 1:
                return self._scan_product(picking, res['lots'].product_id, 1.0, state, lot_name=res['lot_name'])
            return self._feedback('warning', self.env._(
                "Several products have the lot %s: scan the product first.", res['lot_name']))
        return self._feedback('error', self.env._("Unknown barcode: %s", barcode))

    @api.model
    def _location_has_lines(self, picking, location):
        return any(ml.location_id._child_of(location) for ml in picking.move_line_ids)

    @api.model
    def _scan_location(self, picking, location, state):
        source = picking.location_id
        dest = picking.location_dest_id
        in_source = source.usage in ('internal', 'transit') and location._child_of(source)
        in_dest = dest.usage in ('internal', 'transit') and location._child_of(dest)
        pending = self._pending_dest_lines(picking)
        rules = picking.picking_type_id
        as_dest = False
        if in_dest and pending:
            as_dest = not in_source or rules.om_barcode_require_dest or not self._location_has_lines(picking, location)
        if as_dest:
            if location.usage == 'view':
                return self._feedback('error', self.env._(
                    "%s is a view location: scan a location where products can be stored.", location.complete_name))
            for line in pending:
                self._split_scanned(line)
            pending.write({'location_dest_id': location.id, 'om_barcode_dest_scanned': True})
            state.pop('pending_product_id', None)
            return self._feedback('success', self.env._(
                "%(count)s line(s) put in %(location)s.", count=len(pending), location=location.complete_name))
        if in_source:
            if rules.om_barcode_require_dest and pending and dest.usage in ('internal', 'transit'):
                return self._feedback('error', self.env._("Scan the destination of the scanned products first."))
            state['source_location_id'] = location.id
            state['source_location_name'] = location.complete_name
            state.pop('pending_product_id', None)
            return self._feedback('success', self.env._("Picking from %s.", location.complete_name), sound='location')
        if in_dest:
            if picking.picking_type_code == 'incoming' or not in_source:
                return self._feedback('warning', self.env._(
                    "Scan the products to put in %s first.", location.complete_name))
        return self._feedback('error', self.env._(
            "%s is not a location of this transfer.", location.complete_name))

    @api.model
    def _split_scanned(self, line):
        """Keep only the scanned quantity on the line; the rest goes to a new line."""
        rest = line.quantity - line.om_barcode_qty
        if line.uom_id.compare(rest, 0) <= 0 or not line.om_barcode_qty:
            return self.env['stock.move.line']
        vals = line.copy_data({
            'quantity': rest,
            'om_barcode_qty': 0,
            'om_barcode_dest_scanned': False,
            'om_barcode_packed': False,
            'picked': False,
            'result_package_id': line.result_package_id.id if not line.om_barcode_packed else False,
        })[0]
        line.quantity = line.om_barcode_qty
        return self.env['stock.move.line'].create(vals)

    @api.model
    def _scan_package(self, picking, package, state):
        source = picking.location_id
        dest = picking.location_dest_id
        location = package.location_id
        quants = package.contained_quant_ids.filtered(lambda q: q.quantity > 0)
        if location and quants and source.usage in ('internal', 'transit') and location._child_of(source):
            if state.get('source_location_id') and not location._child_of(
                    self.env['stock.location'].browse(state['source_location_id'])):
                return self._feedback('error', self.env._(
                    "Package %(package)s is in %(location)s, not in the scanned location.",
                    package=package.name, location=location.complete_name))
            return self._take_package(picking, package, state)
        if location and quants and not (dest.usage in ('internal', 'transit') and location._child_of(dest)):
            return self._feedback('error', self.env._(
                "Package %(package)s is in %(location)s: it is not part of this transfer.",
                package=package.name, location=location.complete_name))
        lines = self._pending_pack_lines(picking)
        if not lines:
            return self._feedback('warning', self.env._("Scan the products to put in package %s first.", package.name))
        for line in lines:
            self._split_scanned(line)
        lines.write({'result_package_id': package.id, 'om_barcode_packed': True})
        return self._feedback('success', self.env._(
            "%(count)s line(s) put in package %(package)s.", count=len(lines), package=package.name))

    @api.model
    def _take_package(self, picking, package, state):
        packages = self.env['stock.package'].search([('id', 'child_of', package.id)])
        lines = picking.move_line_ids.filtered(lambda ml: ml.package_id in packages)
        if lines and all(ml.uom_id.compare(self._line_done(ml), ml.quantity) >= 0 for ml in lines):
            return self._feedback('error', self.env._("Package %s is already scanned.", package.name))
        products = packages.quant_ids.product_id
        if not lines or set(products.ids) - set(lines.product_id.ids):
            if not picking.picking_type_id.om_barcode_allow_unplanned and \
                    set(products.ids) - set(picking.move_ids.product_id.ids):
                return self._feedback('error', self.env._("Package %s is not in this transfer.", package.name))
            picking.action_add_entire_packs([package.id])
            lines = picking.move_line_ids.filtered(lambda ml: ml.package_id in packages)
        content = sum(packages.quant_ids.mapped('quantity'))
        covered = sum(lines.mapped('quantity'))
        whole = lines and lines[0].uom_id.compare(covered, content) >= 0
        for line in lines:
            vals = {'om_barcode_qty': line.quantity, 'picked': False}
            if whole:
                vals.update(result_package_id=line.package_id.id, om_barcode_packed=True)
            line.write(vals)
        self._trim_surplus(picking)
        return self._feedback('success', self.env._("Package %s taken.", package.name))

    @api.model
    def _trim_surplus(self, picking):
        """Release what is reserved beyond the demand on lines nobody scanned,
        e.g. after a whole package was taken instead of the reserved stock."""
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            excess = sum(ml.uom_id._compute_quantity(ml.quantity, move.uom_id) for ml in move.move_line_ids) \
                - move.product_uom_qty
            if move.uom_id.compare(excess, 0) <= 0:
                continue
            for line in move.move_line_ids.filtered(lambda ml: not self._line_done(ml) and not ml.package_id):
                if move.uom_id.compare(excess, 0) <= 0:
                    break
                qty = line.uom_id._compute_quantity(line.quantity, move.uom_id)
                if move.uom_id.compare(qty, excess) <= 0:
                    excess -= qty
                    line.unlink()
                else:
                    line.quantity = move.uom_id._compute_quantity(qty - excess, line.uom_id)
                    excess = 0

    @api.model
    def _source_location(self, state):
        return self.env['stock.location'].browse(state.get('source_location_id') or []).exists()

    @api.model
    def _quant_qty(self, product, location, lot=None):
        domain = Domain('product_id', '=', product.id) & Domain('location_id', 'child_of', location.id)
        if lot is not None:
            domain &= Domain('lot_id', '=', lot.id)
        quants = self.env['stock.quant'].search(domain)
        return sum(quants.mapped('quantity'))

    @api.model
    def _scan_product(self, picking, product, qty, state, lot_name=None, expiry=None):
        picking_type = picking.picking_type_id
        code = picking.picking_type_code
        source = self._source_location(state)
        source_internal = picking.location_id.usage in ('internal', 'transit')
        if product.type != 'consu':
            return self._feedback('error', self.env._("%s is not a product kept in stock.", product.display_name))
        if picking_type.om_barcode_require_source and source_internal and not source \
                and self.env.user.has_group('stock.group_stock_multi_locations'):
            return self._feedback('warning', self.env._("Scan the source location first."))
        tracked = product.tracking in ('lot', 'serial') and (
            picking_type.use_create_lots or picking_type.use_existing_lots)
        lot_name = self._clean_lot_name(lot_name)
        if tracked and not lot_name:
            state['pending_product_id'] = product.id
            state['pending_product_name'] = product.display_name
            state['pending_qty'] = qty
            if product.tracking == 'serial':
                message = self.env._("Scan the serial number of %s.", product.display_name)
            else:
                message = self.env._("Scan the lot number of %s.", product.display_name)
            return self._feedback('warning', message, sound='ask')
        state.pop('pending_product_id', None)
        state.pop('pending_product_name', None)
        state.pop('pending_qty', None)

        lot = self.env['stock.lot']
        if tracked:
            lot = lot.search(Domain('name', '=', lot_name) & Domain('product_id', '=', product.id)
                             & Domain('company_id', 'in', [picking.company_id.id, False]), limit=1)
            if product.tracking == 'serial':
                if qty != 1:
                    return self._feedback('error', self.env._("A serial number is for one unit only."))
                used = picking.move_line_ids.filtered(
                    lambda ml: ml.product_id == product and (ml.lot_id.name == lot_name or ml.lot_name == lot_name)
                    and self._line_done(ml) > 0)
                if used:
                    return self._feedback('error', self.env._(
                        "Serial number %s is already scanned in this transfer.", lot_name))
                if code == 'incoming' and lot and self.env['stock.quant'].search_count([
                        ('lot_id', '=', lot.id), ('quantity', '>', 0),
                        ('location_id.usage', 'in', ['internal', 'transit'])], limit=1):
                    return self._feedback('error', self.env._("Serial number %s is already in stock.", lot_name))
            if not lot and not picking_type.use_create_lots:
                return self._feedback('error', self.env._(
                    "Lot or serial number %(lot)s does not exist for %(product)s.",
                    lot=lot_name, product=product.display_name))
            if source_internal and product.is_storable:
                where = source or picking.location_id
                if not lot or self._quant_qty(product, where, lot) <= 0:
                    return self._feedback('error', self.env._(
                        "%(lot)s is not in %(location)s.", lot=lot_name, location=where.complete_name))
        elif source and source_internal and product.is_storable:
            if self._quant_qty(product, source) <= 0:
                return self._feedback('error', self.env._(
                    "%(product)s is not in %(location)s.", product=product.display_name,
                    location=source.complete_name))

        line = self._take(picking, product, qty, source, lot, lot_name if tracked else None, expiry)
        if not line:
            return self._feedback('error', self.env._("%s is not in this transfer.", product.display_name))
        state['last_line_id'] = line.id
        return self._feedback('success', self.env._(
            "%(product)s: %(done)s / %(demand)s", product=product.display_name,
            done=self._fmt(line.om_barcode_qty), demand=self._fmt(line.quantity)),
            line_id=line.id)

    @api.model
    def _take(self, picking, product, qty, source, lot, lot_name, expiry):
        """Add ``qty`` (product unit) of ``product`` to the best line of the
        transfer; a reserved line of another lot or location gives up its
        unscanned quantity to a new line when it has to."""
        MoveLine = self.env['stock.move.line']
        lines = picking.move_line_ids.filtered(lambda ml: ml.product_id == product and self._is_open(ml))
        tracked = bool(lot_name)

        def same_lot(ml):
            if not tracked:
                return True
            return (lot and ml.lot_id == lot) or (not ml.lot_id and ml.lot_name == lot_name)

        def same_place(ml):
            return not source or ml.location_id == source or ml.location_id._child_of(source)

        def remaining(ml):
            return ml.quantity - self._line_done(ml)

        def to_line_uom(ml):
            return product.uom_id._compute_quantity(qty, ml.uom_id)

        lot_vals = {}
        if tracked:
            lot_vals = {'lot_id': lot.id} if lot else {'lot_name': lot_name, 'lot_id': False}
            if expiry and 'expiration_date' in MoveLine._fields and not lot:
                lot_vals['expiration_date'] = fields.Datetime.to_datetime(expiry)

        exact = lines.filtered(lambda ml: same_lot(ml) and same_place(ml))
        for line in exact:
            if line.uom_id.compare(remaining(line), 0) > 0:
                return self._add(line, to_line_uom(line))
        # A line without a lot yet (receipts) or reserved elsewhere: adapt it.
        flexible = lines.filtered(lambda ml: ml.uom_id.compare(remaining(ml), 0) > 0).sorted(
            lambda ml: (bool(ml.lot_id or ml.lot_name), not same_place(ml)))
        for line in flexible:
            vals = {} if same_lot(line) else dict(lot_vals)
            if source and not same_place(line):
                vals['location_id'] = source.id
            return self._adapt(line, to_line_uom(line), vals, target=exact[:1])
        for line in exact:
            if product.tracking != 'serial':
                return self._add(line, to_line_uom(line))
        move = picking.move_ids.filtered(lambda m: m.product_id == product and m.state not in ('done', 'cancel'))[:1]
        if not move and not picking.picking_type_id.om_barcode_allow_unplanned:
            return MoveLine
        vals = {
            'picking_id': picking.id,
            'product_id': product.id,
            'location_id': (source or picking.location_id).id,
            'location_dest_id': picking.location_dest_id.id,
            'quantity': qty,
            'om_barcode_qty': qty,
            'uom_id': product.uom_id.id,
            **lot_vals,
        }
        if move:
            vals['move_id'] = move.id
            vals['uom_id'] = move.uom_id.id
            vals['quantity'] = vals['om_barcode_qty'] = product.uom_id._compute_quantity(qty, move.uom_id)
        line = MoveLine.create(vals)
        line._apply_putaway_strategy()
        return line

    @api.model
    def _add(self, line, qty):
        line.write({'om_barcode_qty': self._line_done(line) + qty, 'picked': False})
        return line

    @api.model
    def _adapt(self, line, qty, vals, target=None):
        if not vals:
            return self._add(line, qty)
        done = self._line_done(line)
        if target and target.uom_id == line.uom_id:
            # The same lot and place already has a line: it takes the quantity.
            give = min(line.quantity - done, qty)
            if line.uom_id.compare(line.quantity - give, 0) <= 0 and not done:
                line.unlink()
            else:
                line.quantity = line.quantity - give
            target.write({
                'quantity': target.quantity + qty,
                'om_barcode_qty': self._line_done(target) + qty,
                'picked': False,
            })
            return target
        if not done and line.uom_id.compare(line.quantity, qty) <= 0:
            vals.update(om_barcode_qty=qty, picked=False)
            if line.uom_id.compare(line.quantity, qty) < 0:
                vals['quantity'] = qty
            line.write(vals)
            return line
        give = min(line.quantity - done, qty)
        new_vals = line.copy_data({
            'quantity': qty,
            'om_barcode_qty': qty,
            'picked': False,
            'om_barcode_dest_scanned': False,
            'om_barcode_packed': False,
            'result_package_id': False,
        })[0]
        new_vals.update(vals)
        if line.uom_id.compare(line.quantity - give, 0) <= 0 and not done:
            line.unlink()
        else:
            line.quantity = line.quantity - give
        return self.env['stock.move.line'].create(new_vals)

    # ------------------------------------------------------------------
    # Buttons of the transfer screen
    # ------------------------------------------------------------------

    @api.model
    def picking_set_qty(self, picking_id, line_id, qty, state=None):
        picking = self._get_picking(picking_id)
        state = dict(state or {})
        line = picking.move_line_ids.filtered(lambda ml: ml.id == line_id)
        try:
            with self.env.cr.savepoint():
                if not line:
                    raise UserError(self.env._("This line is not in the transfer anymore."))
                qty = max(float(qty or 0), 0.0)
                tracked = line.product_id.tracking in ('lot', 'serial') and (
                    picking.picking_type_id.use_create_lots or picking.picking_type_id.use_existing_lots)
                if tracked and qty and not (line.lot_id or line.lot_name):
                    raise UserError(self.env._("Scan the lot or serial number of %s.", line.product_id.display_name))
                if line.product_id.tracking == 'serial' and qty > 1:
                    raise UserError(self.env._("A serial number is for one unit only."))
                line.write({'om_barcode_qty': qty, 'picked': False})
                feedback = self._feedback('success', self.env._(
                    "%(product)s: %(qty)s", product=line.product_id.display_name, qty=self._fmt(qty)),
                    line_id=line.id, sound='none')
        except UserError as error:
            feedback = self._feedback('error', str(error.args[0]))
        return self._answer(picking, feedback, state)

    @api.model
    def picking_add_move(self, picking_id, move_id, state=None):
        """+ on a part of a move that is not reserved: a line for one unit."""
        picking = self._get_picking(picking_id)
        state = dict(state or {})
        move = picking.move_ids.filtered(lambda m: m.id == move_id)
        if not move:
            return self._answer(picking, self._feedback('error', self.env._("This product is not in the transfer.")), state)
        return self._answer(picking, self._try(lambda: self._scan_product(picking, move.product_id, 1.0, state)), state)

    @api.model
    def picking_add_product(self, picking_id, product_id, state=None):
        picking = self._get_picking(picking_id)
        state = dict(state or {})
        product = self.env['product.product'].browse(product_id).exists()
        return self._answer(picking, self._try(lambda: self._scan_product(picking, product, 1.0, state)), state)

    @api.model
    def _try(self, func):
        try:
            with self.env.cr.savepoint():
                return func()
        except UserError as error:
            return self._feedback('error', str(error.args[0]))

    @api.model
    def picking_put_in_pack(self, picking_id, state=None):
        picking = self._get_picking(picking_id)
        state = dict(state or {})

        def put_in_pack():
            lines = self._pending_pack_lines(picking)
            if not lines:
                return self._feedback('warning', self.env._("Scan the products to put in a package first."))
            package = self.env['stock.package'].create({})
            for line in lines:
                self._split_scanned(line)
            lines.write({'result_package_id': package.id, 'om_barcode_packed': True})
            return self._feedback('success', self.env._(
                "%(count)s line(s) put in new package %(package)s.", count=len(lines), package=package.name))
        return self._answer(picking, self._try(put_in_pack), state)

    @api.model
    def picking_validate(self, picking_id, state=None):
        picking = self._get_picking(picking_id)
        state = dict(state or {})
        picking_type = picking.picking_type_id
        scanned = self._scanned_lines(picking)
        if not scanned and not any(ml.picked for ml in picking.move_line_ids):
            return self._answer(picking, self._feedback('error', self.env._("Scan the products first.")), state)
        if picking_type.om_barcode_require_dest and picking.location_dest_id.usage in ('internal', 'transit') \
                and any(not ml.om_barcode_dest_scanned for ml in scanned):
            return self._answer(picking, self._feedback(
                'error', self.env._("Scan the destination location of the scanned products.")), state)
        if picking_type.om_barcode_require_package and any(not ml.result_package_id for ml in scanned):
            return self._answer(picking, self._feedback(
                'error', self.env._("Put the scanned products in a package.")), state)
        try:
            with self.env.cr.savepoint():
                for line in scanned:
                    line.write({'quantity': line.om_barcode_qty, 'picked': True})
                action = picking.button_validate()
        except UserError as error:
            return self._answer(picking, self._feedback('error', str(error.args[0])), state)
        if isinstance(action, dict):
            return self._answer(picking, self._feedback('info', ''), state, action=action)
        return self.picking_result(picking.id)

    @api.model
    def picking_result(self, picking_id):
        picking = self.env['stock.picking'].browse(picking_id)
        picking.check_access('read')
        if picking.state != 'done':
            return self._answer(picking, self._feedback('info', ''), {})
        backorders = picking.backorder_ids
        message = self.env._("%s is done.", picking.name)
        if backorders:
            message = self.env._(
                "%(picking)s is done. Backorder: %(backorders)s.",
                picking=picking.name, backorders=', '.join(backorders.mapped('name')))
        return {'type': 'success', 'message': message, 'done': True, 'sound': 'done',
                'picking_type_id': picking.picking_type_id.id}
