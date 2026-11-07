from odoo import api, fields, models


class OmInventoryReport(models.AbstractModel):
    _inherit = 'om.inventory.report'

    @api.model
    def _om_unit_costs(self, product_ids, at, options=None):
        """{(company id, product id): unit cost at ``at``, in the report currency}.

        The cost is Odoo's own valuation (standard, average or FIFO) on that
        date, as on the product: its stock value divided by its quantity.
        """
        costs = {}
        product_ids = list(set(product_ids))
        if not product_ids:
            return costs
        target = self.env.company.currency_id
        today = fields.Date.context_today(self)
        for company in self.env.companies:
            products = self.env['product.product'].with_company(company).with_context(
                allowed_company_ids=company.ids, active_test=False)
            dated = bool(at and at.date() <= today)
            if dated:
                products = products.with_context(to_date=at)
            products = products.browse(product_ids)
            # standard cost: the price of the date, as Odoo values it, in one query;
            # average and FIFO: Odoo's own valuation of the date
            standard = products.filtered(lambda p: p.cost_method == 'standard' and not p.lot_valuated)
            unit_costs = {p.id: p.standard_price for p in standard}
            if dated and standard:
                for product, product_value in standard._get_last_product_value(at).items():
                    unit_costs[product.id] = product_value.value
            for product in products - standard:
                unit_costs[product.id] = product.avg_cost
            for product_id, cost in unit_costs.items():
                if company.currency_id != target:
                    cost = company.currency_id._convert(cost, target, self.env.company, today)
                costs[(company.id, product_id)] = cost
        return costs

    @api.model
    def _om_row_companies(self, rows):
        """{location id: company id} of the rows' locations."""
        location_ids = {r['location_id'] for r in rows if r.get('location_id')}
        locations = self.env['stock.location'].with_context(active_test=False).browse(location_ids)
        return {loc.id: loc.company_id.id for loc in locations}

    @api.model
    def _om_set_values(self, rows, at, pairs, options=None):
        """For each (quantity key, value key) of ``pairs``, the value of the
        quantity at the unit cost of ``at``."""
        if not rows:
            return rows
        chosen = (options or {}).get('columns')
        if chosen and not any(value_key in chosen or value_key + '_cmp' in chosen for _q, value_key in pairs):
            # the value columns are hidden: no valuation to compute
            for row in rows:
                for _quantity_key, value_key in pairs:
                    row[value_key] = 0.0
            return rows
        costs = self._om_unit_costs([r['product_id'] for r in rows if r.get('product_id')], at, options)
        companies = self._om_row_companies(rows)
        default_company = self.env.company.id
        for row in rows:
            company_id = companies.get(row.get('location_id'), default_company)
            cost = costs.get((company_id, row.get('product_id')), 0.0)
            row.setdefault('unit_cost', cost)
            for quantity_key, value_key in pairs:
                row[value_key] = (row.get(quantity_key) or 0.0) * cost
        return rows

    @api.model
    def _om_unit_cost_node(self, node, quantity_key, value_key):
        quantity = node['values'].get(quantity_key) or 0.0
        if len({r.get('product_id') for r in node['rows']}) == 1 and quantity:
            node['values']['unit_cost'] = node['values'].get(value_key, 0.0) / quantity
        else:
            node['values']['unit_cost'] = False
