import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import queries


class OmShopifyImportWizard(models.TransientModel):
    """ Import some orders or products of a store, by number or ID. """
    _name = 'om.shopify.import.wizard'
    _description = 'Import from Shopify by Number'

    store_id = fields.Many2one('om.shopify.store', required=True, domain="[('state', '=', 'connected')]")
    kind = fields.Selection([('order', 'Orders'), ('product', 'Products')], required=True, default='order')
    references = fields.Text(required=True, help="Order numbers (#1001, 1002…) or product IDs, separated by commas, "
                                                 "spaces or new lines.")

    def action_import(self):
        self.ensure_one()
        store = self.store_id
        refs = [r for r in re.split(r'[\s,;]+', self.references or '') if r]
        if not refs:
            raise UserError(_("Enter at least one number."))
        jobs = self.env['om.connector.job']
        for ref in refs:
            if self.kind == 'order':
                name = ref if ref.startswith('#') else f'#{ref}'
                nodes = store._shopify_execute(queries.ORDER_SEARCH, {'query': f'name:{name}'}).get('orders', {}).get('nodes')
                node = next((n for n in nodes or [] if n['name'] == name), None)
                if not node:
                    raise UserError(_("No order %(name)s in %(store)s.", name=name, store=store.name))
                jobs |= store._connector_enqueue('_connector_job_shopify_import_order', {'id': node['id'],
                                                 'updatedAt': node['updatedAt']}, model_name='sale.order',
                                                 name=_("Order %(name)s", name=name), dedupe_key=f"order:{node['id']}")
            else:
                gid = ref if ref.startswith('gid://') else f'gid://shopify/Product/{ref}'
                jobs |= store._connector_enqueue('_connector_job_shopify_import_product', {'id': gid, 'manual': True},
                                                 model_name='om.shopify.product.template',
                                                 name=_("Product %(id)s", id=gid.rsplit('/', 1)[-1]),
                                                 dedupe_key=f'product:{gid}')
        jobs.action_run_now()
        failed = jobs.filtered(lambda j: j.state == 'failed')
        if failed:
            raise UserError('\n'.join(f'{j.name}: {j.error}' for j in failed))
        action = self.env['ir.actions.act_window']._for_xml_id('om_shopify.om_shopify_job_action')
        action['domain'] = [('id', 'in', jobs.ids)]
        action['context'] = {}
        return action
