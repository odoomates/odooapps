# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo import tools


class POSSaleReport(models.Model):
    _name = 'pos.sale.report'
    _auto = False
    _description = "POS Sale Combined View"

    product_id = fields.Many2one('product.product', string="Product")
    partner_id = fields.Many2one('res.partner', string="Customer")
    quantity = fields.Float(string="Quantity")
    price_unit = fields.Float(string="Unit Price")
    date = fields.Datetime(string="Date")
    type = fields.Selection(selection=[('sales', 'Sales'), ('pos', 'Point Of Sales')], string='Type')

    @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self._cr, 'pos_sale_report')
        self._cr.execute("""
            CREATE OR REPLACE VIEW pos_sale_report AS (
            
                SELECT row_number() OVER () AS id, line.product_id, line.partner_id,
                line.quantity, line.price_unit, line.date, line.type FROM (
                
                    SELECT sol.product_id, so.partner_id, sol.product_uom_qty as quantity,
                    sol.price_unit, so.confirmation_date as date,
                    'sales' as type
                    FROM sale_order_line sol
                    LEFT JOIN sale_order so ON (so.id = sol.order_id)
                    WHERE so.state in ('done', 'sale')
                    
                    UNION ALL
                    
                    SELECT pol.product_id, po.partner_id, pol.qty as quantity, 
                    pol.price_unit, po.date_order as date,
                    'pos' as type
                    FROM pos_order_line as pol
                    LEFT JOIN pos_order po ON (po.id = pol.order_id)
                    WHERE po.state in ('paid', 'done', 'invoiced')
                    
                ) line
                
            )""")

