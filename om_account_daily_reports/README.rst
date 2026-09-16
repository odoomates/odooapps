===============================
Odoo 20 Daily Financial Reports
===============================

This module adds three daily accounting reports to Odoo 20 Community Edition:
the day book, the cash book and the bank book.

Features
========

* Print a Day Book PDF that lists the journal items day by day for a date
  range.
* Print a Cash Book PDF for the cash accounts, with the accounts of the cash
  journals and of their payment methods proposed by default.
* Print a Bank Book PDF for the bank accounts, with the accounts of the bank
  journals and of their payment methods proposed by default.
* Restrict any of the reports to the journals and the accounts you select.
* Choose the target moves: posted entries only or all entries.
* Add an initial balance row to the cash book and the bank book when a start
  date is set.
* Sort the cash book and the bank book lines by date or by journal and
  partner.
* Show all accounts, only the ones with movements or only the ones whose
  balance is not zero.
* The journals of the current company are proposed by default in the three
  wizards.
* The report wizards are available to the accounting readonly group and to the
  accounting manager group.

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

There is nothing to configure.

The module depends on the Odoo 20 Accounting Financial Reports module
(accounting_pdf_reports), which is installed with it.


Usage
=====

Go to Accounting > Reporting > Daily Reports and pick Day Book, Cash Book or
Bank Book.

Set the start and end date, keep or change the proposed journals and accounts,
choose the other options of the wizard, then click the print button to get the
PDF.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
