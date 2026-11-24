====================================
Odoo 19 Accounting Financial Reports
====================================

This Module will provide all the financial reports for odoo 19
community edition

Tax Report
==========

* Print a Tax Report for a period picked from shortcuts (this or last month,
  quarter or fiscal year) or for any custom date range.
* Count a cash basis tax in the period of the payment, not of the invoice.
* Print the taxes withheld on payments (Community's
  ``l10n_account_withholding_tax``) in a Withholding section of their own,
  their base counted once.
* Print the Tax Report By Tax Grid: the tax return of your country as its
  fiscal localization lays it out, grid by grid, with its totals, ready to
  copy into the tax office's portal. Some 95 localizations ship one, among
  them Belgium, France, Germany, the Netherlands, Spain, the United Kingdom,
  India, Saudi Arabia, the United Arab Emirates, Mexico and Australia.
* Close a tax period: a draft entry that clears the tax accounts of the period
  against a tax payable or receivable account.

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

There is Nothing to Configure

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
menu too. The accounting managers add the menus; the menu shows for the users
who see the statement reports.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates