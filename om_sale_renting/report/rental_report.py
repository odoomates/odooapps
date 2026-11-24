from odoo import fields, models, tools
from odoo.tools.sql import SQL

from ..models.sale_order_line import RENTAL_LINE_STATUS


class OmRentalReport(models.Model):
    _name = 'om.rental.report'
    _description = "Rental Analysis"
    _auto = False
    _order = 'date desc'

    date = fields.Date(string="Day", readonly=True)
    order_id = fields.Many2one('sale.order', string="Order", readonly=True)
    order_line_id = fields.Many2one('sale.order.line', string="Order Line", readonly=True)
    partner_id = fields.Many2one('res.partner', string="Customer", readonly=True)
    user_id = fields.Many2one('res.users', string="Salesperson", readonly=True)
    team_id = fields.Many2one('crm.team', string="Sales Team", readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", readonly=True)
    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string="Product Template", readonly=True)
    categ_id = fields.Many2one('product.category', string="Product Category", readonly=True)
    rental_line_status = fields.Selection(RENTAL_LINE_STATUS, string="Status", readonly=True)
    quantity = fields.Float(string="Units Rented", readonly=True, aggregator='sum',
                            help="Units rented on the day (summed over days: unit-days).")
    revenue = fields.Monetary(string="Revenue", readonly=True, aggregator='sum', currency_field='currency_id',
                              help="Untaxed amount of the rental line spread over its days, in company currency.")
    capacity = fields.Float(string="Rentable Units", readonly=True, aggregator='max')
    utilisation = fields.Float(
        string="Utilisation (%)", readonly=True, aggregator='avg',
        help="Share of the rentable quantity in use, on the days the product is rented.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %s AS (
                WITH line AS (
                    SELECT
                        sol.id,
                        sol.order_id,
                        sol.product_id,
                        sol.company_id,
                        sol.rental_line_status,
                        sol.rental_start_date,
                        sol.rental_return_date,
                        sol.product_uom_qty * COALESCE(lu.factor, 1) / NULLIF(COALESCE(pu.factor, 1), 0)
                            AS qty,
                        sol.price_subtotal / CASE COALESCE(so.currency_rate, 0)
                            WHEN 0 THEN 1.0 ELSE so.currency_rate END AS amount,
                        GREATEST(1, (DATE_TRUNC('day', sol.rental_return_date - INTERVAL '1 second')::date
                                     - DATE_TRUNC('day', sol.rental_start_date)::date) + 1) AS days
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    JOIN product_product pp ON pp.id = sol.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    LEFT JOIN uom_uom lu ON lu.id = sol.product_uom_id
                    LEFT JOIN uom_uom pu ON pu.id = pt.uom_id
                    WHERE sol.is_rental
                      AND so.state = 'sale'
                      AND sol.rental_start_date IS NOT NULL
                      AND sol.rental_return_date IS NOT NULL
                )
                SELECT
                    (line.id * 100000 + (day.day::date - DATE_TRUNC('day', line.rental_start_date)::date))
                        AS id,
                    day.day::date AS date,
                    line.order_id,
                    line.id AS order_line_id,
                    so.partner_id,
                    so.user_id,
                    so.team_id,
                    line.company_id,
                    company.currency_id,
                    line.product_id,
                    pt.id AS product_tmpl_id,
                    pt.categ_id,
                    line.rental_line_status,
                    line.qty AS quantity,
                    line.amount / line.days AS revenue,
                    pt.rental_qty AS capacity,
                    CASE WHEN COALESCE(pt.rental_qty, 0) > 0
                        THEN line.qty * 100.0 / pt.rental_qty ELSE NULL END AS utilisation
                FROM line
                JOIN sale_order so ON so.id = line.order_id
                JOIN res_company company ON company.id = line.company_id
                JOIN product_product pp ON pp.id = line.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                CROSS JOIN LATERAL GENERATE_SERIES(
                    DATE_TRUNC('day', line.rental_start_date),
                    DATE_TRUNC('day', line.rental_return_date - INTERVAL '1 second'),
                    INTERVAL '1 day'
                ) AS day(day)
            )
        """, SQL.identifier(self._table)))
