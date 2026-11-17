from odoo import _, fields, models


class OmShopifyExportWizard(models.TransientModel):
    """ Export the selected Odoo products to Shopify. """
    _name = 'om.shopify.export.wizard'
    _description = 'Export Products to Shopify'

    store_ids = fields.Many2many('om.shopify.store', string='Stores', required=True,
                                 domain="[('state', '=', 'connected')]",
                                 default=lambda self: self.env['om.shopify.store'].search(
                                     [('state', '=', 'connected')], limit=1))
    template_ids = fields.Many2many('product.template', string='Products', required=True,
                                    default=lambda self: self.env.context.get('active_ids'))
    images = fields.Boolean(string='Send the Images', default=True)

    def action_export(self):
        self.ensure_one()
        count = 0
        for store in self.store_ids:
            for template in self.template_ids:
                store._connector_enqueue('_connector_job_shopify_export_product',
                                         {'template_id': template.id, 'images': self.images,
                                          'at': fields.Datetime.to_string(fields.Datetime.now())},
                                         model_name='om.shopify.product.template',
                                         name=_("Export %(product)s", product=template.name),
                                         dedupe_key=f'export:{template.id}')
                count += 1
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': _("%(count)s export(s) queued: follow them in Shopify > Jobs.", count=count),
                       'type': 'info', 'next': {'type': 'ir.actions.act_window_close'}},
        }
