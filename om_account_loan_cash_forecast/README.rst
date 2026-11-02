=====================================
Loans and Leases in the Cash Forecast
=====================================

This module links Loans and Leases (om_account_loan) with Cash Forecast
(om_account_cash_forecast) in Odoo 20 Community Edition: the instalments and
the lease payments still to come are expected in the cash forecast. It is
installed automatically when both modules are installed.

Features
========

* Loan instalments: the instalments of the running loans not paid yet, on
  their due dates, for the instalment less the tax withheld (what leaves the
  bank), on a row of their own in the payments.
* Lease payments not yet billed: the payments of the running leases not billed
  yet, on their due dates, with the taxes of the bills (and the tax withheld on
  the interest). Once billed, a lease payment is a vendor bill of the forecast,
  expected on the due date of the bill.
* In the currency of the company, at the rate of the starting date of the
  forecast, as the other items. The instalments already due follow the Overdue
  option of the forecast.
* The draft and closed loans, and the paid instalments (in the bank already),
  are left out.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. It installs by itself when
Loans and Leases and Cash Forecast are both installed.

Usage
=====

Print the cash forecast (Accounting > Reporting > Management > Cash Forecast):
the Loan instalments and Lease payments not yet billed rows show with the
other payments.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
