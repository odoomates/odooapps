=======================
Odoo 20 Reconciliation
=======================

This module adds a bank reconciliation screen and a journal item matching tool
to Odoo 20 Community Edition, together with an automatic reconciliation that
runs in the background.

Features
========

* Reconcile bank and cash transactions on a dedicated screen: pick a journal,
  filter on To Reconcile, Reconciled or All, and search a transaction by label,
  partner or amount.
* See for the selected transaction the open journal items that are likely to be
  its counterpart, ranked by amount, reference, partner and direction.
* Search the open journal items yourself when no suggestion fits, and match one
  item, several items, or only a part of the amount of an item.
* Add a counterpart by hand with its account, label, partner, taxes and analytic
  distribution; the taxes of the counterpart are computed and posted with it.
* Apply a reconciliation model on the transaction to fill in the counterparts
  from its lines.
* Preview the journal items of the reconciliation and the amount left to cover
  before validating; what is not covered stays on the suspense account.
* Undo the reconciliation of a transaction, and mark a transaction to check or
  reviewed for a colleague.
* Open the screen on one journal from the Reconcile button on the bank and cash
  cards of the accounting dashboard.
* Reconcile new transactions automatically: partner mapping models fill in the
  partner, reconciliation models with the automatic trigger are applied, and a
  transaction matching exactly one open item by amount and reference is
  reconciled on its own.
* Run the automatic reconciliation from a scheduled action that treats the
  transactions in batches every day, and that is triggered again as soon as new
  transactions are created or imported. A transaction that fails is logged and
  does not stop the others.
* Match open journal items outside the bank: a list of the open items of
  reconcilable accounts, grouped by account and partner, with a Match button.
* Match the selected items in a wizard showing the debit, the credit and the
  difference, and write the difference off on a journal, account, date and label
  of your choice; without a write-off the items are matched partially.
* Let the Match Suggestions action reconcile, in one go, the groups of open
  items of a same account and partner whose amounts cancel each other.
* The bank and cash cards of the accounting dashboard show what is left to do:
  a Reconcile button with the number of transactions to reconcile, the balance
  of the last statement and the transactions marked to check.
* Type transactions in from the New Transaction button of a bank or cash card,
  and the cash counted at the end of the day, with its transactions, from the
  New Statement button of a cash card. The transactions and the statements get
  a list and a form of their own.
* Only users of the accounting group can reconcile, and a transaction or a group
  of items being reconciled is locked so that two users cannot reconcile it
  twice.

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

In Accounting > Configuration > Settings, in the Bank & Cash section, the option
Reconcile New Transactions Automatically decides whether new transactions are
reconciled in the background. It is on by default and is set per company.

Define your reconciliation models if you want bank fees, rounding differences or
recurring counterparts to be proposed or applied automatically.


Usage
=====

Go to Accounting > Accounting > Reconciliation > Bank Reconciliation, select a
transaction, check the proposed items or search for others, add a counterpart
when needed and validate.

To match open items that did not come from the bank, go to Accounting >
Accounting > Reconciliation > Open Items, or to Match Journal Items in the same
menu, select the items of one account and press Match.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
