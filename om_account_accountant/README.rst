==============================
Odoo 20 Accounting Community
==============================

Odoo 20 Community Edition ships Invoicing, not Accounting. This module turns it
into a full accounting application: it installs the seventeen Odoo Mates
accounting modules in one click and adds the menus, groups, settings and
dashboards that make them work as one system rather than seventeen separate
apps.

A 47-page user guide ships with the module, at
``static/description/user_guide.pdf``. It covers setting up, the daily work,
bank reconciliation, assets, budgets, closing and every report, with the
screens shown at each step.


Requirements
============

* Odoo 20.0 Community Edition.
* No external Python library and no paid Odoo Enterprise module.


What it installs
================

Reports and analysis
--------------------

* ``accounting_pdf_reports`` — Balance Sheet, Profit and Loss, Cash Flow
  Statement, General Ledger, Partner Ledger, Trial Balance, Aged Partner
  Balance, Journal Audit and Tax Report.
* ``om_account_daily_reports`` — Day Book, Bank Book and Cash Book.
* ``om_account_cash_forecast`` — a forecast of the cash position from the
  receivables, the payables and the recurring entries.

Management
----------

* ``om_account_asset`` — asset categories, asset registers, depreciation boards
  and the depreciation schedule.
* ``om_account_budget`` — budgets, budgetary positions and budget analysis.
* ``om_recurring_payments`` — recurring entry templates and their generation.
* ``om_account_followup`` — follow-up levels, follow-up reports and customer
  statements.

Bank and payments
-----------------

* ``om_account_reconcile`` — the reconciliation screen and Match Journal Items.
* ``om_account_bank_statement_import`` — statement import with reusable file
  maps.
* ``om_account_check_printing`` — cheque formats and cheque printing.

Currency and periods
--------------------

* ``om_currency_rate_update`` — automatic currency rates from the configured
  provider.
* ``om_currency_revaluation`` — the revaluation of the balances held in a
  foreign currency.
* ``om_fiscal_year`` — fiscal years, lock dates and period closing.

Dashboards
----------

* ``om_spreadsheet_account``, ``om_spreadsheet_account_asset``,
  ``om_spreadsheet_account_budget``, ``om_spreadsheet_account_followup`` — the
  accounting overview, profit and loss, balance sheet, receivables and
  payables, bank and cash, assets, budgets, follow-ups and cash forecast
  dashboards.


What this module adds on top
============================

* Renames the Invoicing application to Accounting.
* Arranges the menus of all the installed apps into one coherent structure: the
  daily work under Accounting, the reports under Reporting, the settings under
  Configuration, and a Management section for the assets, budgets, recurring
  payments and closing.
* Adds a Journals menu grouping the sales, purchase, bank and cash, and
  miscellaneous journal entries.
* Adds a Bank and Cash menu with the bank statements and the cash registers.
* Adds an Account Tags menu to the accounting configuration.
* Adds a Payment Methods menu, read-only, for users in developer mode.
* Shows the payment account column on the payment methods of a journal, so the
  account used by each method is visible from the journal form.
* Lets journals be created from their list; the accounting dashboard only shows
  them.
* Makes the Journal Items menu available to every accounting user and moves it
  to the top of its menu.
* Adds a Reconcile action on the journal items list, for accountants.
* Renames the accounting groups to Accountant, Advisor and Auditor, and makes an
  Advisor an Accountant as well.
* Adds the Anglo-Saxon Accounting option to the accounting settings, to record
  the cost of a good as an expense when it is invoiced to the customer.
* Keeps the In Payment status on invoices, so a registered payment does not mark
  the invoice paid before the payment is reconciled.


Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Installing this module installs the seventeen modules listed above, so make
sure they are all present in your addons folder before you start.


Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Upgrade the modules it installs at the same time, so the menus and the groups
stay consistent.


Configuration
=============

There is nothing to configure in this module itself.

1. Give your users the Accountant, Advisor or Auditor access rights.
2. Install a chart of accounts from Accounting > Configuration > Settings.
3. Configure the modules it installs from Accounting > Configuration: the fiscal
   year, the cheque formats, the currency provider, the follow-up levels and the
   statement import file maps.

The user guide walks through each of these in order.


Usage
=====

Open the Accounting application. The menus of the installed modules are grouped
under Accounting, Reporting and Configuration, and the dashboards are available
from the Dashboards application.


Frequently asked questions
==========================

**The invoice stays In Payment after I register a payment. Why?**

That is deliberate. An invoice is only marked Paid once the payment is
reconciled with the bank statement. To skip that step and go straight to Paid,
see https://www.youtube.com/watch?v=eWxfy86Byog

**Do I need Odoo Enterprise?**

No. Everything here runs on Community Edition.

**Where are the reports?**

Under Accounting > Reporting. The PDF financial reports, the ledgers, the day,
bank and cash books, the tax report and the ageing reports are all there.


Bug Tracker
===========

Please report issues to odoomates@gmail.com, or open an issue on
https://github.com/odoomates/odooapps


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>
* Odoo SA


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates

* YouTube: https://www.youtube.com/c/OdooMates
* Email: odoomates@gmail.com
