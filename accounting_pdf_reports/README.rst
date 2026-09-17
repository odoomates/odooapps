====================================
Odoo 20 Accounting Financial Reports
====================================

This module adds a set of PDF accounting reports to Odoo 20 Community Edition:
balance sheet, profit and loss, cash flow, ledgers, trial balance, tax and
journal reports.

Features
========

* Print a Balance Sheet and a Profit and Loss report built from an account
  report structure that you can edit yourself.
* Compare a financial report with another date range and optionally print the
  debit and credit columns next to the balance.
* Print a Cash Flow Statement split into operating, investing and financing
  activities, either as a summary or detailed by account.
* Set a Cash Flow Activity on an account to place it in another section of the
  cash flow statement than the one derived from its account type.
* Print a General Ledger with an optional initial balance row, sorted by date
  or by journal and partner.
* Print a Trial Balance filtered by accounts, partners and analytic accounts.
* Print a Partner Ledger for receivable accounts, payable accounts or both,
  with an option to include reconciled entries and a currency column.
* Print an Aged Partner Balance as of a date, with a period length in days
  that you choose, plus separate Aged Receivable and Aged Payable menus.
* Print a Tax Report for a date range.
* Print a Journals Audit report with the entries sorted by date or by journal
  entry number and an optional currency column.
* Print a Journals Entries PDF directly from the print menu of journal
  entries.
* Print a Balance Statement (Partner Ledger) from the print menu of a
  customer or vendor.
* Filter every report by company, journals, start and end date and target
  moves, either all posted entries or all entries.
* Open the General Ledger and the Partner Ledger as list, pivot and graph
  views on journal items from the Ledgers menu.
* Maintain the account report structures used by the financial reports, with
  parent and child lines, a sign, a display style and a level of detail.
* Report wizards are available to the accounting readonly, billing, user and
  manager groups, depending on the report.

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

The module installs a default Balance Sheet and Profit and Loss structure, so
the reports can be printed right after the installation.

If you want to change what a financial report contains, edit the report lines
in Accounting > Configuration > Accounting > Financial Reports.

If an account has to appear in another section of the cash flow statement than
the one of its account type, set the Cash Flow Activity field on the account
form.


Usage
=====

Go to Accounting > Reporting and pick the report you need:

* Statement Reports: Balance Sheet, Profit and Loss, Cash Flow Statement
* Partner Reports: Partner Ledger, Aged Partner Balance, Aged Receivable,
  Aged Payable
* Taxes & Fiscal: Tax Report
* Audit Reports: General Ledger, Trial Balance, Journals Audit

Fill in the dates, the journals and the other options of the wizard, then
click the print button to get the PDF.

The journal items of the General Ledger and of the Partner Ledger can also be
browsed on screen from Accounting > Accounting > Ledgers > General Ledger Items
and Partner Ledger Items.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
