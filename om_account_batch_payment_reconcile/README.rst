=============================
Batch Payments Reconciliation
=============================

This module is the bridge between *Batch Payments* (``om_account_batch_payment``) and *Odoo 19
Reconciliation* (``om_account_reconcile``), in Odoo 19 Community Edition: one transaction of the bank is
reconciled with all the payments of a batch at once. It installs itself when both modules are installed.


Features
========

The module adds a Batches tab to the reconciliation screen of *Odoo 19 Reconciliation*
(``om_account_reconcile``):

* The tab lists the sent batches of the bank going in the direction of the transaction. Clicking a batch
  adds the open items of all its payments to the proposal; any of them can be removed again before
  validating, e.g. when the bank rejected one payment.
* The batch is suggested on its own when its reference is in the label of the transaction, or when its
  amount is the amount of the transaction and no other open item or batch has it.
* The automatic reconciliation reconciles a transaction with a batch whose reference is in the label and
  whose amount is the amount of the transaction.
* A payment with a journal entry is cleared by its outstanding item. A payment without journal entry (a
  payment method without an outstanding account, the default with *Odoo 19 Accounting Community*) is
  cleared with the open items of the invoices it pays, and what it pays beyond them goes to the partner;
  it is marked as paid when the transaction covers the whole batch.
* The batch is reconciled once the bank cleared every one of its payments, and back to sent when a
  reconciliation is undone.
* The Bank Transactions button of a batch opens the transactions that cleared its payments.

Usage
=====

Open the reconciliation screen, select the transaction of the bank and open the Batches tab, or accept the
batch suggested for the transaction, then validate.

Credits
=======

* Odoo Mates <odoomates@gmail.com>
