# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    enable_service_charge = fields.Boolean(string='Service Charges')
    service_charge_type = fields.Selection([('amount', 'Amount'),
                                            ('percentage', 'Percentage')],
                                           string='Type', default='amount')
    service_charge = fields.Float(string='Service Charge')
    service_product_id = fields.Many2one('product.product', string='Service Product',
                                         domain="[('available_in_pos', '=', True),"
                                                "('sale_ok', '=', True), ('type', '=', 'service')]")

    @api.onchange('enable_service_charge')
    def set_config_service_charge(self):
        if self.enable_service_charge:
            if not self.service_product_id:
                domain = [('available_in_pos', '=', True), ('sale_ok', '=', True),  ('type', '=', 'service')]
                self.service_product_id = self.env['product.product'].search(domain, limit=1)
            self.service_charge = 10.0
        else:
            self.service_product_id = False
            self.service_charge = 0.0
