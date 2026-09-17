=============================
Odoo 20 Accounting Dashboards
=============================

This module adds accounting dashboards to the Dashboards app of Odoo 20 Community Edition. They are
spreadsheets computed from the account types, so they work with any chart of accounts, and they sit in
the Finance section next to the Invoicing dashboard of Odoo.

Features
========

* Accounting Overview: revenue, gross profit, expenses, net profit, bank and cash, receivables,
  payables and current ratio of the period, compared with the comparison period, and the revenue and
  expenses by month.
* Profit and Loss: revenue, other income, cost of revenue, operating expenses, depreciation, other
  expenses, net profit and margins for the period, the comparison period and each month of the period.
* Balance Sheet: assets, liabilities and equity at the end of the period compared with the end of the
  comparison period, with the earnings of the current year and of the years not closed yet, and the
  current ratio, quick ratio and debt to equity ratio.
* Receivables and Payables: the open balances by age (not due, 1-30, 31-60, 61-90 and over 90 days),
  the days sales and payables outstanding, the invoiced and billed amounts by month, and the customers
  and vendors with the largest overdue balance.
* Bank and Cash: the balance of the bank and cash accounts, the cash in and out by month, and the
  transactions left to reconcile by journal.
* The statements cover any period chosen in the Period filter (the fiscal year to date by default)
  and are compared, in the Compare With filter, with the same period last year or with the previous
  period: the quarter before a quarter, the months before a number of months.
* A Partner filter on the receivables and payables, and a Journal filter on the bank and cash.
* All the figures add up the companies selected in the company switcher.
* The OM.ACCOUNT.BALANCE spreadsheet formula gives the balance of account types over any period for
  the selected companies, e.g. =OM.ACCOUNT.BALANCE("income,income_other", "01/01/2026", "03/31/2026").
* A database without accounting entries yet shows sample dashboards.
* Accounting auditors and administrators see the dashboards; billing users see the receivables and
  payables only.
* The Assets, Budgets and Follow-ups and Cash Forecast dashboards come with the modules
  om_spreadsheet_account_asset, om_spreadsheet_account_budget and om_spreadsheet_account_followup,
  installed automatically with the asset, budget, follow-up and cash forecast apps.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.


Configuration
=============

There is nothing to configure: the dashboards read the account types of the chart of accounts. Check
that the accounts have the right type (Bank and Cash, Receivable, Current Assets, Income, Expenses...)
for the figures to land in the right lines.

The dashboards are written by ``tools/build_dashboards.py``. After changing a dashboard there, run
``python3 om_spreadsheet_account/tools/build_dashboards.py`` to write the files of ``data/files`` again.
The samples are exported from a database with demo data by ``tools/export_samples.py``, which needs
Playwright.

Usage
=====

Go to Dashboards and pick a dashboard of the Finance section. Change the period, the partner or the
journal in the filters. The receivables, payables, bank and asset figures open the documents behind
them when clicked.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
