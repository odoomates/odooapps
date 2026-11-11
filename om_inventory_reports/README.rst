=================
Inventory Reports
=================

Inventory reports on screen in Odoo 20 Community, with the filters at the top,
groups that unfold, drill-down to the moves, saved views, and export to PDF,
Excel and CSV as the report is shown.

Reports
=======

* **Overview**: the key figures of every report; a card opens its report, a
  figure opens it filtered.
* **Stock on Hand**: today from the quants (on hand, reserved, available, with
  the quants of each product), or on any past date from the done moves.
* **Stock by Warehouse**: products down, one column per warehouse.
* **Stock Card**: per product, the opening balance, each receipt and issue with
  its reference, partner and date, the running balance and the closing balance.
* **Inventory Summary**: opening, received from vendors, produced, customer
  returns, adjustments, transfers in, delivered to customers, consumed in
  production, returned to vendors, scrapped, transfers out, closing.
* **Negative Stock**: quantities below zero, by location.
* **Reorder Report**: the reordering rules below their minimum, with the
  forecast and the quantity to order.
* **Stock Ageing**: stock by age bucket from the incoming date of the quants
  (days per bucket of your choice) and the average age.
* **Slow-Moving & Dead Stock**: products in stock with their last issue and the
  days without one: dead (never issued), slow, moving.
* **ABC Analysis**: products ranked by consumption value (or quantity), classes
  A, B and C with your own thresholds.
* **Stock Turnover**: what was used against the average stock, and the days of
  cover of the closing stock.
* **Transfers**: by operation type and status, late transfers, transfers done
  late, average delay, and each transfer.
* **Adjustments & Scrap**: what inventory adjustments found or lost, and what
  was scrapped.

On screen
=========

* Periods: today, this week, month, quarter, year, the previous ones, or a
  custom range; arrows move to the previous or next period. "As of" reports take
  one date.
* Filters on warehouses, locations (with or without their sub-locations),
  products, categories, lots, owners, partners and operation types.
* Group by up to three levels, in any order.
* Key figures above the table; a figure with a filter shows only its lines.
* Compare with the previous period or the same period last year (Stock on
  Hand, Stock by Warehouse, Inventory Summary, Stock Turnover, Transfers,
  Adjustments & Scrap): previous, change and change in % columns, and the change
  on the key figures.
* Sort by any column; show, hide and reorder the columns; compact or
  comfortable rows; search in the report.
* Header, first column and total stay in place while scrolling.
* Rows open their record (move, transfer, quant, product...); the "..." menu
  opens the product in another report with the same period.
* Keyboard: arrows move between rows, right and left unfold and fold, Enter
  opens, "/" goes to the search.
* Back from a record through the breadcrumb, the report is as it was left.

Saved views and exports
=======================

* Save the filters, grouping and columns under a name, open one by default,
  share it with the other users.
* PDF (company layout, A4 landscape), Excel (numbers and dates, groups as Excel
  outline levels, frozen header, filters on the header row) and CSV, with the
  lines unfolded on screen or with every line.
* **Scheduled Reports**: send a saved view by email every day, week or month,
  as PDF, Excel or CSV, with the access rights of the user of your choice.

Related modules
===============

* **Inventory Reports - Valuation** (installs with Accounting stock valuation):
  stock values in the reports and a Stock Valuation report at any date.
* **Inventory Reports - Expiry** (installs with expiration dates): a Lot Expiry
  report.

Usage
=====

Inventory > Reporting > Inventory Reports. The Reporting menu of Inventory is
shown to the Inventory administrators.

Credits
=======

Odoo Mates, odoomates@gmail.com
