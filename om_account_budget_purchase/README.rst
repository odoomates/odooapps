=======================================
Odoo 20 Budget Management - Purchase
=======================================

This module brings purchase orders into the budget follow-up of Odoo 20
Community Edition: what is ordered but not billed yet is shown as committed, and
orders going over budget are signalled or blocked.

Features
========

* Adds a Committed column on the expense lines of a budget, holding the amount
  of the confirmed purchase orders counted by the line and not billed yet.
* Counts an order line against a budget line through the expense account of its
  product and its analytic distribution, converted to the currency of the
  company at the date of the order approval.
* Moves an amount from committed to actual as the vendor bills are posted; a
  draft bill changes neither of the two.
* Shows a warning on a purchase order that is still to confirm, naming the
  budget lines it would push over their planned amount and by how much.
* Blocks the confirmation of such an order for everybody but the accounting
  managers when the company blocks the documents over budget; the error names
  the budget lines concerned.
* Adds the Committed column, and takes the committed amounts into account in the
  remaining amounts, of the Budget vs Actual report printed from a budget.
* Installs itself as soon as the budget management and the purchase application
  are both installed.

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

Decide in Accounting > Configuration > Settings whether the documents over
budget are only signalled or blocked, with the option Block Documents Over
Budget. It is off by default and is set per company.

The committed amounts follow the expense account of the products and the
analytic distribution of the order lines, so make sure your products have an
expense account and that your buyers fill in the analytic distribution used by
the budget lines.


Usage
=====

Open a validated budget from Accounting > Accounting > Budgets and read the
Committed column next to the planned and the actual amounts of its expense
lines.

Encode a purchase order as usual. A warning appears on the order while it is not
confirmed when it does not fit in the budget, and, when the company blocks them,
only an accounting manager can confirm it.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
