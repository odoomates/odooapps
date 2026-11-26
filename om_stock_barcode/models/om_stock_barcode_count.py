from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class OmStockBarcode(models.AbstractModel):
    _inherit = 'om.stock.barcode'

    # ------------------------------------------------------------------
    # Inventory count
    # ------------------------------------------------------------------

    @api.model
    def get_count_locations(self):
        """Locations with a count due (cycle counts) or requested."""
        today = fields.Date.context_today(self)
        Quant = self.env['stock.quant']
        base = Domain('location_id.usage', 'in', ['internal', 'transit']) & Domain(
            'company_id', 'in', self.env.companies.ids)
        due = Quant._read_group(
            base & Domain('inventory_date', '<=', today) & Domain('quantity', '!=', 0),
            ['location_id'], ['__count'])
        requested = Quant._read_group(base & Domain('inventory_quantity_set', '=', True), ['location_id'], ['__count'])
        rows = {}
        for location, count in due:
            rows.setdefault(location, {'due': 0, 'counted': 0})['due'] = count
        for location, count in requested:
            rows.setdefault(location, {'due': 0, 'counted': 0})['counted'] = count
        scheduled = self.env['stock.location'].search(
            Domain('usage', '=', 'internal') & Domain('next_inventory_date', '<=', today)
            & Domain('company_id', 'in', self.env.companies.ids), limit=50)
        for location in scheduled:
            rows.setdefault(location, {'due': 0, 'counted': 0})
        result = [{
            'id': location.id,
            'name': location.complete_name,
            'due': values['due'],
            'counted': values['counted'],
            'next': fields.Date.to_string(location.next_inventory_date) if location.next_inventory_date else '',
        } for location, values in rows.items()]
        result.sort(key=lambda row: row['name'])
        return {'locations': result[:100], 'settings': self._settings()}

    @api.model
    def _count_location(self, location_id):
        location = self.env['stock.location'].browse(location_id).exists()
        if not location or location.usage not in ('internal', 'transit'):
            raise UserError(self.env._("Scan an internal location to count it."))
        return location

    @api.model
    def get_count(self, location_id):
        location = self._count_location(location_id)
        quants = self.env['stock.quant'].search(
            Domain('location_id', 'child_of', location.id) & Domain('company_id', 'in', self.env.companies.ids)
            & (Domain('quantity', '!=', 0) | Domain('inventory_quantity_set', '=', True)),
            order='location_id, product_id, lot_id', limit=500)
        lines = []
        for quant in quants:
            counted = quant.inventory_quantity if quant.inventory_quantity_set else None
            lines.append({
                'id': quant.id,
                'product': self._product_data(quant.product_id),
                'location': self._loc(quant.location_id),
                'lot': quant.lot_id.name or '',
                'package': quant.package_id.name or '',
                'quantity': self._qty(quant.quantity, quant.uom_id),
                'counted': None if counted is None else self._qty(counted, quant.uom_id),
                'diff': self._qty(quant.inventory_diff_quantity, quant.uom_id) if quant.inventory_quantity_set else 0,
                'uom': quant.uom_id.name,
                'outdated': quant.is_outdated,
            })
        return {
            'location': self._loc(location),
            'lines': lines,
            'counted': sum(1 for line in lines if line['counted'] is not None),
            'differences': sum(1 for line in lines if line['counted'] is not None and line['diff']),
            'settings': self._settings(),
        }

    @api.model
    def _count_answer(self, location, feedback, state):
        feedback.update(state=state, count=self.get_count(location.id))
        return feedback

    @api.model
    def count_open(self, barcode):
        """The first scan of a count: the location to count."""
        res = self._resolve(barcode)
        location = res.get('location')
        if not location or location.usage not in ('internal', 'transit'):
            return self._feedback('error', self.env._("Scan an internal location to count it."))
        return {'type': 'success', 'message': location.complete_name, 'location_id': location.id}

    @api.model
    def count_scan(self, location_id, barcode, state=None):
        location = self._count_location(location_id)
        state = dict(state or {})
        try:
            with self.env.cr.savepoint():
                feedback = self._count_scan(location, barcode, state)
        except UserError as error:
            feedback = self._feedback('error', str(error.args[0]))
        if feedback.get('location_id'):
            location = self.env['stock.location'].browse(feedback['location_id'])
        return self._count_answer(location, feedback, state)

    @api.model
    def _count_scan(self, root, barcode, state):
        res = self._resolve(barcode)
        current = self.env['stock.location'].browse(state.get('location_id') or root.id).exists() or root
        if res.get('location') and not res.get('product'):
            location = res['location']
            if location.usage not in ('internal', 'transit'):
                return self._feedback('error', self.env._("%s is not an internal location.", location.complete_name))
            state['location_id'] = location.id
            state['location_name'] = location.complete_name
            state.pop('package_id', None)
            state.pop('pending_product_id', None)
            if location._child_of(root):
                return self._feedback('success', self.env._("Counting in %s.", location.complete_name), sound='location')
            # Another place altogether: the count moves there.
            return self._feedback('success', self.env._("Counting in %s.", location.complete_name),
                                  sound='location', location_id=location.id)
        if res.get('package') and not res.get('product'):
            package = res['package']
            state['package_id'] = package.id
            state['package_name'] = package.name
            return self._feedback('success', self.env._("Counting in package %s.", package.name), sound='location')
        pending = self.env['product.product'].browse(state.get('pending_product_id') or []).exists()
        product = res.get('product')
        lot_name = res.get('lot_name')
        qty = res.get('qty') or 1.0
        if not product and pending:
            product, lot_name, qty = pending, lot_name or barcode, state.get('pending_qty') or 1.0
        if not product and res.get('lots'):
            if len(res['lots'].product_id) > 1:
                return self._feedback('warning', self.env._(
                    "Several products have the lot %s: scan the product first.", res['lot_name']))
            product = res['lots'].product_id
        if not product:
            return self._feedback('error', self.env._("Unknown barcode: %s", barcode))
        if not product.is_storable:
            return self._feedback('error', self.env._("%s is not tracked in stock.", product.display_name))
        lot_name = self._clean_lot_name(lot_name)
        if product.tracking in ('lot', 'serial') and not lot_name:
            state.update(pending_product_id=product.id, pending_product_name=product.display_name, pending_qty=qty)
            if product.tracking == 'serial':
                return self._feedback('warning', self.env._("Scan the serial number of %s.", product.display_name), sound='ask')
            return self._feedback('warning', self.env._("Scan the lot number of %s.", product.display_name), sound='ask')
        for key in ('pending_product_id', 'pending_product_name', 'pending_qty'):
            state.pop(key, None)
        lot = self.env['stock.lot']
        if lot_name:
            lot = lot.search(Domain('name', '=', lot_name) & Domain('product_id', '=', product.id)
                             & Domain('company_id', 'in', [current.company_id.id, False]), limit=1)
            if not lot:
                lot = lot.create({'name': lot_name, 'product_id': product.id, 'company_id': current.company_id.id})
        package = self.env['stock.package'].browse(state.get('package_id') or []).exists()
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quant = Quant.search(
            Domain('product_id', '=', product.id) & Domain('location_id', '=', current.id)
            & Domain('lot_id', '=', lot.id) & Domain('package_id', '=', package.id)
            & Domain('owner_id', '=', False), limit=1)
        counted = (quant.inventory_quantity if quant.inventory_quantity_set else 0.0) + qty
        warning = False
        if product.tracking == 'serial':
            if qty != 1 or counted > 1:
                return self._feedback('error', self.env._("Serial number %s is already counted.", lot_name))
            elsewhere = self.env['stock.quant'].search(
                Domain('lot_id', '=', lot.id) & Domain('quantity', '>', 0)
                & Domain('location_id.usage', 'in', ['internal', 'transit'])
                & Domain('location_id', '!=', current.id), limit=1)
            if elsewhere:
                warning = self.env._("Serial number %(lot)s is recorded in %(location)s.",
                                     lot=lot_name, location=elsewhere.location_id.complete_name)
        if quant:
            quant.write({'inventory_quantity': counted, 'user_id': self.env.uid})
        else:
            quant = Quant.create({
                'product_id': product.id,
                'location_id': current.id,
                'lot_id': lot.id,
                'package_id': package.id,
                'inventory_quantity': counted,
                'user_id': self.env.uid,
            })
        state['last_quant_id'] = quant.id
        message = self.env._("%(product)s: %(qty)s counted", product=product.display_name,
                             qty=self._fmt(counted))
        if warning:
            return self._feedback('warning', message + '. ' + warning, quant_id=quant.id)
        return self._feedback('success', message, quant_id=quant.id)

    @api.model
    def count_set_qty(self, location_id, quant_id, qty, state=None):
        location = self._count_location(location_id)
        state = dict(state or {})
        quant = self.env['stock.quant'].with_context(inventory_mode=True).browse(quant_id).exists()
        try:
            with self.env.cr.savepoint():
                if not quant:
                    raise UserError(self.env._("This line is not in the count anymore."))
                if qty is None or qty is False or qty == '':
                    quant.action_clear_inventory_quantity()
                else:
                    qty = max(float(qty), 0.0)
                    if quant.product_id.tracking == 'serial' and qty > 1:
                        raise UserError(self.env._("A serial number is for one unit only."))
                    quant.write({'inventory_quantity': qty, 'user_id': self.env.uid})
                feedback = self._feedback('success', '', quant_id=quant.id, sound='none')
        except UserError as error:
            feedback = self._feedback('error', str(error.args[0]))
        return self._count_answer(location, feedback, state)

    @api.model
    def count_apply(self, location_id, state=None):
        location = self._count_location(location_id)
        state = dict(state or {})
        quants = self.env['stock.quant'].with_context(inventory_mode=True).search(
            Domain('location_id', 'child_of', location.id) & Domain('inventory_quantity_set', '=', True)
            & Domain('company_id', 'in', self.env.companies.ids))
        if not quants:
            return self._count_answer(location, self._feedback('error', self.env._("Count some products first.")), state)
        try:
            with self.env.cr.savepoint():
                differences = len(quants.filtered(lambda q: q.inventory_diff_quantity))
                action = quants.action_apply_inventory()
        except UserError as error:
            return self._count_answer(location, self._feedback('error', str(error.args[0])), state)
        if isinstance(action, dict):
            return self._count_answer(location, self._feedback('info', ''), state) | {'action': action}
        return self._count_answer(location, self._feedback('success', self.env._(
            "Count applied: %(count)s line(s), %(diff)s difference(s).", count=len(quants), diff=differences),
            sound='done', applied=True), state)
