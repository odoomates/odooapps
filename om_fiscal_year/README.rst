===============================
Odoo 20 Fiscal Year & Lock Date
===============================

This module adds fiscal years, a year-end closing, a period closing checklist
and a lock date wizard to Odoo 20 Community Edition.

Features
========

* Define fiscal years per company with a start and an end date; overlapping
  fiscal years of the same company are refused.
* Define fiscal years shorter or longer than a year once the Fiscal Years
  option is enabled in the accounting settings.
* Close a fiscal year with a wizard that shows the earnings to transfer, the
  draft entries, the bank transactions still to reconcile, the previous fiscal
  years left open and the points blocking the closing.
* The closing posts a journal entry moving the unallocated earnings from the
  Current Year Earnings account to the retained earnings account you choose,
  and stores the account on the company.
* Optionally set the global lock date to the end of the year when it is
  closed.
* Reopen a closed fiscal year: the closing entry is reversed and the year goes
  back to open.
* A closing entry cannot be reset to draft, cancelled or deleted, and the
  dates and company of a closed fiscal year cannot be changed.
* Only accounting administrators can close or reopen a fiscal year.
* Prepare a period closing with a checklist combining automatic checks and
  manual tasks, tracked in the chatter of the closing.
* The automatic checks count the draft entries of the period, the bank
  transactions not reconciled, the payments and suspense items not matched,
  the bank and cash accounts with a negative balance and the bills that might
  be duplicates; refresh them at any time and open the records behind a check.
* The manual tasks are copied from the closing tasks when the closing is
  created, and each one can be marked as done or back to do.
* Closing a period is refused while a blocking check is not clear or a task is
  not done.
* Choose what the closing locks: nothing, the sales and purchases, the taxes,
  or everything except for the administrators.
* Reopening a period puts the lock dates back to the value they had before the
  closing, and asks you to reopen the later closed periods first.
* Maintain the list of closing tasks, shared by the companies or for one
  company; the module installs eleven tasks for a month-end closing.
* Set the tax, sales, purchase, global and permanent lock dates of the company
  from a single wizard, reserved to accounting administrators.
* Fiscal years, period closings, their checks and the closing tasks are
  restricted to the allowed companies by record rules.

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

In Accounting > Configuration > Settings, set the last day and the last month
of your fiscal year, and tick Fiscal Years if your fiscal years do not last
exactly one year or if you want to manage them one by one.

The same settings page holds the lock dates of the company.

Review the closing tasks in Accounting > Configuration > Accounting > Closing
Tasks and add, edit or archive them so that the checklist matches your own
closing procedure. The tasks installed by the module are left as they are by
the module updates.


Usage
=====

Create your fiscal years in Accounting > Configuration > Accounting > Fiscal
Year.

To close a year, go to Accounting > Accounting > Closing > Year-End Closing,
open the fiscal year, click the closing button, check the figures, pick the
journal and the retained earnings account and confirm.

To close a month, go to Accounting > Accounting > Closing > Period Closing,
create the closing of the period, work through the checklist and close it.

Lock dates can also be changed directly from Accounting > Accounting > Lock
Dates.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
