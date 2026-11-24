==============================
Odoo 20 Accounting Community
==============================

Odoo 20 Community Edition ships Invoicing, not Accounting. This module turns it
into a full accounting application: it installs the seventeen Odoo Mates
accounting modules in one click and adds the menus, groups, settings and
dashboards that make them work as one system rather than seventeen separate
apps.

A 49-page user guide ships with the module, at
``static/description/user_guide.pdf``. It covers setting up, the daily work,
bank reconciliation, assets, budgets, closing and every report, with the
screens shown at each step.


Requirements
============

* Odoo 20.0 Community Edition.
* No external Python library and no paid Odoo Enterprise module.
* To read scanned and photographed vendor bills: ``sudo apt install
  tesseract-ocr poppler-utils``. The PDFs with a text layer need nothing more.


What it installs
================

Reports and analysis
--------------------

* ``accounting_pdf_reports`` — Balance Sheet, Profit and Loss, Cash Flow
  Statement, General Ledger, Partner Ledger, Trial Balance, Aged Partner
  Balance, Journal Audit and Tax Report, and your own financial reports, each
  in a menu of its own.
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
* ``om_account_bill_ocr`` — vendor bills read from their PDF, scan or photo,
  on your own server.

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


Companion modules, installed separately
---------------------------------------

These modules are not dependencies of this one, so installing it does not
install them. They are free on the Odoo Apps store; download the ones you need
into your addons folder and install them from the Apps menu. The user guide
covers them too.

* ``om_account_batch_payment`` — Batch Payments: batch payments and deposits,
  the bulk upload file of the bank and one bank transaction reconciled with a
  whole batch. With this module installed, its bridge
  ``om_account_batch_payment_reconcile`` installs itself and adds the batches
  to the reconciliation screen.
  https://apps.odoo.com/apps/modules/20.0/om_account_batch_payment
* ``om_dynamic_reports`` — Dynamic Accounting Reports: the reports on screen,
  with filters, comparison, horizontal groups, drill-down and export; with the
  assets, the budgets and the currency revaluation, their own reports come with
  it. https://apps.odoo.com/apps/modules/20.0/om_dynamic_reports
* ``om_account_deferred`` — Deferred Revenue and Expense: revenue and expense
  spread over the months they belong to from the start and end dates of the
  invoice and bill lines, with the Deferred Revenue and Deferred Expense
  reports. https://apps.odoo.com/apps/modules/20.0/om_account_deferred
* ``om_account_pdc`` — Post-dated Cheques: the cheques received and issued,
  registered against their invoices, then deposited, cleared or bounced, with
  the cheque register. https://apps.odoo.com/apps/modules/20.0/om_account_pdc
* ``om_account_budget_purchase`` — Budget Control of Purchases: committed
  amounts and budget control on purchase orders. It installs itself when
  Purchase and the budgets are both present. https://apps.odoo.com/apps/modules/20.0/om_account_budget_purchase


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
* Adds a Split action on the journal items, spreading an item over other
  accounts: in place on a draft entry, by a reclassification entry on a posted
  one, so that the posted books stay as they were.
* Adds a signature on the customer invoices: the name and the signature of the
  signing user, the salesperson of the invoice by default. Each user draws or
  uploads their signature in their preferences.
* Adds a New Journal menu: choose what the journal is for (bank, credit card,
  cash, sales, purchase or miscellaneous), and its name, short code and, for a
  bank, its account number are proposed.
* Adds a Document column to the vendor bills list: the eye opens the scan of the
  bill over the list, to check the bills against their documents.


Recurring entries
=================

Odoo repeats a journal entry, a vendor bill or a customer invoice by itself, for
accruals, rent, fees or any amount that comes back every period:

1. Create the entry, the bill or the invoice as usual.
2. In its Other Info tab, set Auto-post to Monthly, Quarterly or Yearly, and an
   Auto-post until date if the recurrence must stop.
3. Post it. Odoo creates the entry of the next period at once, in draft, on the
   same day of the month, and posts it by itself on its date; posting that one
   creates the next, until the Auto-post until date.

To stop a recurrence, set Auto-post to No on the next entry, which is still in
draft, or delete it. To change the amount from the next period on, change it on
that entry. Recurring payments to and from a bank, with their own schedule, are
the job of Recurring Payments (``om_recurring_payments``).


Custom financial reports
========================

Beside the Balance Sheet and the Profit and Loss, build reports of your own (a
management P&L, operating expenses, a gross margin) and open each one from a
menu of its own:

1. In Configuration > Accounting > Financial Reports, create a report and add
   its sections: accounts, account types, the value of another report, or the
   sum of the sections below. Each section has its sign and its level of
   detail.
2. On the form of the report, click **Add to Menu** and pick the menu name, the
   parent menu and the position among its menus.
3. Open the new menu: the report wizard opens with the report chosen. Set the
   dates, a comparison if you need one, and print. With Dynamic Accounting
   Reports (``om_dynamic_reports``) installed, the same menu opens the report on
   screen.

**Remove Menu** takes the menu away again, and deleting the report removes its
menu too. The Advisors add the menus; the menu shows for the users
who see the statement reports.


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

Version 1.6.0 adds fields to the companies, the invoices and the users: upgrade
it, together with Odoo 20 Reconciliation 1.1.0, before using it. From the command
line::

    odoo-bin -c <your config> -d <your database> -u om_account_accountant,om_account_reconcile --stop-after-init

The signature on invoices is off on the existing companies until it is turned
on in the settings.


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

**Does it handle withholding taxes?**

Yes, with the Community module ``l10n_account_withholding_tax`` from the
Apps menu: it withholds the tax on the payment, and the Tax Report prints it in
a Withholding section of its own.


Release Notes
=============

1.7.0
-----

* New Journal: a journal created from what it is for.
* Vendor bills list: preview of the document of each bill.
* User guide: the new reports, the assets, the deferrals and the lock dates.
* No new field on existing records: upgrade with ``-u om_account_accountant``.

1.6.0
-----

* Split a journal item over other accounts: in place on a draft entry, by a
  reclassification entry on a posted one (Action > Split).
* Signature on invoices: the name and the signature of the signing user, the
  salesperson by default, printed on the customer invoices.
* New fields: upgrade with ``-u om_account_accountant,om_account_reconcile``
  (see Upgrade).

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
