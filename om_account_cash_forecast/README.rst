=====================
Odoo 20 Cash Forecast
=====================

This module prints a cash forecast for Odoo 20 Community Edition: starting from the balance of the
Bank and Cash accounts, it shows the receipts and payments expected week by week or month by month
and the resulting closing balance.

Features
========

* Print a PDF cash forecast by week or by month, for 1 to 60 periods from a starting date of your choice.
* The forecast starts from the opening balance of the Bank and Cash accounts, computed from the posted
  entries dated before the starting date.
* Open customer invoices and vendor bills are expected on their due date, for their residual amount.
* Invoices and bills already due are shown in a separate Overdue column, or left out of the forecast.
* Draft invoices and bills can be included, expected on their due date like the posted ones.
* Payments registered but not yet reconciled with the bank (outstanding receipts and payments accounts)
  are listed on their own lines.
* Bank and cash entries already recorded with a date inside the forecast are included.
* Cash forecast items you enter by hand (salaries, rent, loan repayments, taxes) are added to the
  forecast, once or repeated every week, month, quarter or year, with an optional end date.
* Each expected item can be entered in another currency; it is converted to the company currency at
  the rate of the starting date of the forecast.
* When the module om_recurring_payments is installed, its draft recurring payment lines are shown on
  separate recurring receipt and payment lines.
* An option details each line by partner, showing who is expected to pay or to be paid in each period.
* The report prints the opening balance, the totals of the receipts and payments, the net cash flow and
  the closing balance of every period, and warns when the balance is expected to go negative.
* When the module accounting_excel_reports is installed, a Print Excel button exports the same forecast.
* Accounting billing users can read and change the cash forecast items; accounting read-only users can
  read them.
* Cash forecast items belong to a company and are only visible to the users of that company.

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

There is nothing to configure. The forecast reads the invoices, bills, payments and bank entries that
are already in the database.

If you expect receipts or payments that are not in an invoice or a bill, add them under
Accounting > Accounting > Cash Forecast Items: a description, the amount, whether it is a
receipt or a payment, the date it is expected on and, when it comes back, how often it repeats.

Usage
=====

Go to Accounting > Reporting > Management > Cash Forecast, choose the starting date, weeks or months,
the number of periods and the options for the overdue and draft documents, then click Print.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
