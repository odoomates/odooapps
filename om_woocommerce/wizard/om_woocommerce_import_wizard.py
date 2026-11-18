import re

from odoo import _, fields, models
from odoo.exceptions import UserError


class OmWoocommerceImportWizard(models.TransientModel):
    """ Import some orders or products of a store, by number or ID. """
    _name = 'om.woocommerce.import.wizard'
    _description = 'Import from WooCommerce by Number'

    store_id = fields.Many2one('om.woocommerce.store', required=True, domain="[('state', '=', 'connected')]")
    kind = fields.Selection([('order', 'Orders'), ('product', 'Products')], required=True, default='order')
    references = fields.Text(required=True, help="Order numbers (1001, #1002…) or product IDs, separated by commas, "
                                                 "spaces or new lines.")

    def _order_id(self, ref):
        """ The ID of the order numbered ``ref``: the number is the ID, unless an extension numbers the
        orders. """
        store = self.store_id
        data = store._woo_get(f'orders/{ref}') if ref.isdigit() else None
        if data and str(data.get('number')) == ref:
            return data['id']
        for order in store._woo_get('orders', {'search': ref, 'status': 'any', '_fields': 'id,number'}) or []:
            if str(order.get('number')) == ref:
                return order['id']
        if data:
            return data['id']
        raise UserError(_("No order %(ref)s in %(store)s.", ref=ref, store=store.name))

    def action_import(self):
        self.ensure_one()
        store = self.store_id
        refs = [r.lstrip('#') for r in re.split(r'[\s,;]+', self.references or '') if r.lstrip('#')]
        if not refs:
            raise UserError(_("Enter at least one number."))
        jobs = self.env['om.connector.job']
        for ref in refs:
            if self.kind == 'order':
                woo_id = self._order_id(ref)
                jobs |= store._connector_enqueue('_connector_job_woo_import_order', {'id': woo_id},
                                                 model_name='sale.order', name=_("Order %(number)s", number=ref),
                                                 dedupe_key=f'order:{woo_id}')
            else:
                if not ref.isdigit():
                    raise UserError(_("%(ref)s is not a product ID.", ref=ref))
                jobs |= store._connector_enqueue('_connector_job_woo_import_product', {'id': int(ref)},
                                                 model_name='om.woocommerce.product.template',
                                                 name=_("Product %(id)s", id=ref), dedupe_key=f'product:{ref}')
        jobs.action_run_now()
        failed = jobs.filtered(lambda j: j.state == 'failed')
        if failed:
            raise UserError('\n'.join(f'{j.name}: {j.error}' for j in failed))
        action = self.env['ir.actions.act_window']._for_xml_id('om_woocommerce.om_woocommerce_job_action')
        action['domain'] = [('id', 'in', jobs.ids)]
        action['context'] = {}
        return action
