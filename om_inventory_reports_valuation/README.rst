=============================
Inventory Reports - Valuation
=============================

Adds the stock value to the Inventory Reports, and a **Stock Valuation**
report: quantity, unit cost, value and share of value on any date, by category,
product, warehouse, location, lot or owner.

The values are Odoo's stock valuation (standard price, average cost or FIFO) on
the chosen date, as on the products.

Values in the other reports
===========================

* Stock on Hand: the value of the stock.
* Inventory Summary: opening and closing value.
* Stock Card: the value of each receipt and issue (its share of the value Odoo
  booked for the move), a running value, the opening and closing valuation, and
  the revaluations and cost changes of the period on their own line.
* Stock Turnover: closing value.
* Stock Valuation and Inventory Summary can be compared with an earlier period.
* Stock Ageing: the value, and the value of the stock older than the last buckets.
* Slow-Moving & Dead Stock: the value of the dead and of the slow stock.
* ABC Analysis: the products are ranked by their cost at the end of the period.
* Adjustments & Scrap: the net value, at the unit cost of the end of the period.

Installs on its own with Inventory Reports when stock_account is installed.

Credits
=======

Odoo Mates, odoomates@gmail.com
