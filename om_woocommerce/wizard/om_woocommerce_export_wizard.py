from odoo import _, fields, models


class OmWoocommerceExportWizard(models.TransientModel):
    """ Export the selected Odoo products to WooCommerce. """
    _name = 'om.woocommerce.export.wizard'
    _description = 'Export Products to WooCommerce'

    store_ids = fields.Many2many('om.woocommerce.store', string='Stores', required=True,
                                 domain="[('state', '=', 'connected')]",
                                 default=lambda self: self.env['om.woocommerce.store'].search(
                                     [('state', '=', 'connected')], limit=1))
    template_ids = fields.Many2many('product.template', string='Products', required=True,
                                    default=lambda self: self.env.context.get('active_ids'))
    images = fields.Boolean(string='Send the Images', default=True)
    images_possible = fields.Boolean(compute='_compute_images_possible')

    def _compute_images_possible(self):
        for wizard in self:
            wizard.images_possible = any(store._woo_images_possible() for store in wizard.store_ids)

    def action_export(self):
        self.ensure_one()
        self.store_ids._woo_ensure_connected()
        count = 0
        for store in self.store_ids:
            for template in self.template_ids:
                store._woo_enqueue_export(template, images=self.images)
                count += 1
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': _("%(count)s export(s) queued: follow them in WooCommerce > Jobs.", count=count),
                       'type': 'info', 'next': {'type': 'ir.actions.act_window_close'}},
        }
