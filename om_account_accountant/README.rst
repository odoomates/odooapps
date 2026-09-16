==================
Odoo 20 Accounting
==================

This module turns Odoo 20 Community Edition into a full accounting application:
it installs the Odoo Mates accounting modules together and adds the menus,
groups and options that make them work as one.


Common FAQ
==========
1. How to skip in payment status and directly move to paid status ?
a) https://www.youtube.com/watch?v=eWxfy86Byog


Features
========

* Installs, in one click, the financial PDF reports, the asset management, the
  budgets, the fiscal year, the recurring payments, the daily reports, the
  customer follow-ups and the bank reconciliation of the Odoo Mates accounting
  suite.
* Renames the Invoicing application to Accounting.
* Adds a Journals menu grouping the sales, purchase, bank and cash, and
  miscellaneous journal entries.
* Adds a Bank and Cash menu with the bank statements and the cash registers.
* Adds an Account Tags menu to the accounting configuration.
* Adds a Payment Methods menu, in read-only, for users in developer mode.
* Adds a Templates menu to the configuration, for users in developer mode.
* Makes the Journal Items menu available to every accounting user and moves it
  to the top of its menu.
* Adds a Reconcile action on the journal items list, for accountants.
* Renames the accounting groups to Accountant, Advisor and Auditor, and makes an
  Advisor an Accountant as well.
* Adds the Anglo-Saxon Accounting option to the accounting settings, to record
  the cost of a good as an expense when it is invoiced to the customer.
* Keeps the In Payment status on invoices, so a registered payment does not mark
  the invoice paid before the payment is reconciled.
* Shows the payment account column on the payment methods of a journal, so the
  account used by each method is visible from the journal form.

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

There is nothing to configure in this module itself. Give your users the
Accountant, Advisor or Auditor access rights, and configure the modules it
installs from Accounting > Configuration.


Usage
=====

Open the Accounting application. The menus of the installed modules are added to
Accounting, Reporting and Configuration.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
