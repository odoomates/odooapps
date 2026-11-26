from odoo import fields, models
from odoo.fields import Domain


class MrpProduction(models.Model):
    _name = 'mrp.production'
    _inherit = ['mrp.production', 'om.quality.document.mixin']

    om_quality_check_ids = fields.One2many('om.quality.check', 'production_id', string='Quality Check Records')
    om_quality_evaluated = fields.Boolean(copy=False, help="The control points of the order were looked at.")

    def _om_quality_check_domain(self):
        return Domain('production_id', 'in', self.ids)

    def _om_quality_document_of_check(self, check):
        return check.production_id

    def action_confirm(self):
        res = super().action_confirm()
        self._om_quality_create_checks_production()
        return res

    def _action_confirm_mo_backorders(self):
        res = super()._action_confirm_mo_backorders()
        self._om_quality_create_checks_production()
        return res

    def _om_quality_create_checks_production(self):
        """ The checks of the order and of its work order steps. Once per lot points of tracked
        products wait for the finished lots, at production. """
        productions = self.filtered(lambda p: not p.om_quality_evaluated and p.state not in ('draft', 'cancel', 'done'))
        if not productions:
            return self.env['om.quality.check']
        productions.sudo().om_quality_evaluated = True
        Point = self.env['om.quality.point']
        created = self.env['om.quality.check']
        for production in productions:
            product = production.product_id
            points = Point._get_points('production', production.company_id)
            points = points.filtered(lambda p: not p.picking_type_ids or production.picking_type_id in p.picking_type_ids)
            for point in points._filter_product(product):
                if point.frequency == 'lot' and product.tracking != 'none':
                    continue
                if not point._should_check(product):
                    continue
                created |= production._om_quality_create_checks(point, product, None, {
                    'production_id': production.id,
                    'quantity': production.product_qty,
                })
            step_points = Point._get_points('workorder', production.company_id)._filter_product(product)
            for workorder in production.workorder_ids:
                for point in step_points._filter_workorder(workorder):
                    if not point._should_check(product):
                        continue
                    created |= workorder._om_quality_create_checks(point, product, None, {
                        'production_id': production.id,
                        'workorder_id': workorder.id,
                        'workcenter_id': workorder.workcenter_id.id,
                        'quantity': production.product_qty,
                    })
        return created

    def _om_quality_create_lot_checks(self):
        """ Points once per lot: a check for each finished lot or serial number not checked yet. """
        Check = self.env['om.quality.check']
        created = Check
        for production in self.filtered(lambda p: p.state not in ('done', 'cancel') and p.lot_producing_ids):
            product = production.product_id
            points = self.env['om.quality.point']._get_points(
                'production', production.company_id, [('frequency', '=', 'lot')])
            points = points.filtered(lambda p: not p.picking_type_ids or production.picking_type_id in p.picking_type_ids)
            for point in points._filter_product(product):
                for lot in production.lot_producing_ids:
                    domain = Check._om_quality_lot_domain(product, lot=lot) & Domain('point_id', '=', point.id) \
                        & Domain('state', '!=', 'cancel')
                    if Check.sudo().search_count(domain, limit=1):
                        continue
                    created |= production._om_quality_create_checks(point, product, None, {
                        'production_id': production.id,
                        'lot_id': lot.id,
                        'quantity': 1.0 if product.tracking == 'serial' else production.qty_producing,
                    })
        return created

    def pre_button_mark_done(self):
        self._om_quality_create_lot_checks()
        blocking = self._om_quality_blocking_checks()
        if blocking:
            return blocking.production_id._om_quality_block_action(blocking)
        return super().pre_button_mark_done()

    def button_mark_done(self):
        res = super().button_mark_done()
        checks = self.om_quality_check_ids.filtered(lambda c: c.state == 'failed' or c.disposition)
        checks._om_quality_apply_lot_state()
        return res

    def action_om_quality_dialog(self):
        self._om_quality_create_lot_checks()
        return super().action_om_quality_dialog()
