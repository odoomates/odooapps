=======================
Odoo 18 Reconciliation
=======================

This module adds a bank reconciliation screen and a journal item matching tool
to Odoo 18 Community Edition, together with an automatic reconciliation that
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
  partner, the reconciliation models set to auto-validate are applied, and a
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
* Find the partner of a new transaction, only when it is certain: the one
  partner owning the bank account of the other party, the one company with
  exactly the name written by the bank, or the one partner of the open invoice
  or bill whose number is in the reference. When several partners fit, or when
  they disagree, the partner is left empty.
* Match an invoice paid at its discounted amount within its early payment
  discount date in full, the discount going to the early payment discount
  account.
* Find a payment from the cheque number written on the transaction, and show
  and search the cheque numbers in the list of items, with cheque printing
  installed.
* Match items differing by a small amount within a payment tolerance, and items
  in another currency within a percentage; the difference of an automatic
  reconciliation goes to a payment difference account.
* Keep a transaction open on the receivable or the payable of its partner, e.g.
  an advance to match with the invoice later.
* See the messages, the activities and the attachments of a transaction on the
  screen, and create a draft bill or invoice of its amount from a document.
* Tick several transactions to set their partner, or to book them on an account.
* Match a transaction of the bank from the outstanding credits of the invoice.
* Learn a reconciliation model once transactions of the same partner, or with
  the same first word in their label, are booked by hand on the same account
  three times; count the times each model is used; offer a "Bank Fees" model on
  every bank journal; try a new or changed automatic model again on the open
  transactions.
* Match items of two accounts, or of several partners, after a journal entry
  moving them to the account and the partner chosen; take taxes out of a
  write-off; fill a write-off in from a reconciliation model; date the entries
  after the lock date; refuse partial matching when asked.
* Reconcile Automatically: the perfect pairs, or the items of a partner adding
  up to zero, on chosen accounts, partners and dates.

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

Version 1.2.0 adds fields to the companies and to the reconciliation models:
upgrade the module before using it, or the server stops on the missing
columns. From the command line::

    odoo-bin -c <your config> -d <your database> -u om_account_reconcile --stop-after-init

The new settings get their default values on the existing companies: finding
the partner of new transactions is on, the tolerances are zero (off), and the
payment difference and bank fees accounts are empty.


Configuration
=============

In Accounting > Configuration > Settings, in the Bank & Cash section, the option
Reconcile New Transactions Automatically decides whether new transactions are
reconciled in the background. It is on by default and is set per company.

Define your reconciliation models if you want bank fees, rounding differences or
recurring counterparts to be proposed or applied automatically.

In the same section:

* Find the Partner of New Transactions, on by default.
* Payment Tolerance: an amount, a percentage for the items in another currency,
  and the account of the difference of an automatic reconciliation.
* Bank Fees: the account of the "Bank Fees" model offered on every bank journal.


Usage
=====

Go to Accounting > Accounting > Reconciliation > Bank Reconciliation, select a
transaction, check the proposed items or search for others, add a counterpart
when needed and validate.

To match open items that did not come from the bank, go to Accounting >
Accounting > Reconciliation > Open Items, or to Match Journal Items in the same
menu, select the items of one account and press Match.


Release Notes
=============

1.2.0
-----

* Partner of new transactions found when it is certain (bank account, exact
  company name, invoice reference); left empty otherwise.
* Early payment discounts, cheque numbers, payment and foreign currency
  tolerances in the matching.
* Transactions of the bank in the outstanding credits of the invoices.
* Learned reconciliation models, use count, "Bank Fees" models, automatic models
  tried again on the open transactions.
* Match Journal Items: transfer between accounts or partners, taxes on the
  write-off, model presets, lock date, partial matching option; Reconcile
  Automatically.
* Reconciliation screen: notes and documents, bill or invoice from a document,
  several transactions at once, keep on the partner's receivable or payable.
* New fields: upgrade the module with ``-u om_account_reconcile`` (see Upgrade).

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
