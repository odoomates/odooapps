# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    enable_tax_return = fields.Boolean(string='Tax Return')
#    service_charge_tax_calculation = fields.Boolean(string='Include taxes for calculation?',required=True,default=True)
#    service_charge_type = fields.Selection([('amount', 'Amount'),
#                                            ('percentage', 'Percentage')],
#                                           string='Type', default='amount')
    tax_return_type = fields.Many2one('account.tax', string='Tax Return Type')
    tax_return_product_id = fields.Many2one('product.product', string='Tax Return Product',
                                         domain="[('available_in_pos', '=', True),"
                                                "('sale_ok', '=', True), ('type', '=', 'service')]")
    tax_return_charge = fields.Float(string='Tax Charge')
#    service_product_id = fields.Many2one('product.product', string='Service Product',
#                                         domain="[('available_in_pos', '=', True),"
#                                                "('sale_ok', '=', True), ('type', '=', 'service')]")

    @api.onchange('enable_tax_return')
    def set_config_service_charge(self):
        if self.enable_tax_return:
            if not self.tax_return_product_id:
                domain = [('available_in_pos', '=', True), ('sale_ok', '=', True),  ('type', '=', 'service')]
                self.tax_return_product_id = self.env['product.product'].search(domain, limit=1)
            if not self.tax_return_type:
                domain = [('type_tax_use','=','sale')] 
                self.tax_return_type = self.env['account.tax'].search(domain, limit=1)
            self.tax_return_charge = self.tax_return_type.amount
        else:
            self.service_product_id = False
            self.service_charge = 0.0

    @api.onchange('tax_return_type')
    def set_config_service_charge(self):
        if self.enable_tax_return:
            self.tax_return_charge = self.tax_return_type.amount
        else:
            self.tax_return_product_id = False
            self.tax_return_charge = 0.0
