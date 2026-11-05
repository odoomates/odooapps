======================
Odoo 18 Batch Payments
======================

This module groups the payments of a bank journal in batches, in Odoo 18 Community Edition: a payment run
to the vendors sent to the bank in one file, or a deposit of customer cheques taken to the bank at once.
The bank then shows one transaction for the whole batch, and that one transaction is reconciled with all
the payments of the batch.

Features
========

* Batch Payments under Vendors and Batch Deposits under Customers, numbered BATCH/OUT/2026/0001 and
  BATCH/IN/2026/0001.
* Create a batch from the list of payments (select the payments, then Action > Create Batch), from the
  Register Payment window of several bills or invoices (tick Create a Batch), or from the batch itself
  by adding the payments.
* The payments of a batch share the bank journal, the direction, the payment method and the currency;
  a payment is in one batch at most.
* Validate the batch: its draft payments are posted, the bank file is generated, the payments are marked
  as sent and locked: the amount, partner, bank account, date and memo of a sent payment cannot change
  until the batch is set back to draft.
* A rejected or cancelled payment stays listed in its batch but no longer counts in its total.
* Bank file layouts designed from the settings, for the bulk upload of any bank: CSV or Excel, the
  delimiter, quotes, encoding, header row, date format, decimal separator or amounts in cents, and the
  columns in the order of the template of the bank, each with its title, a maximum length and capitals.
  The columns can be the line number, payment number, batch reference, payment date, partner name,
  reference, tax ID, email, phone, city and country, the account holder name, account number, BIC / SWIFT
  / IFSC and bank name of the partner, the amount, currency, memo, the account number of the company or a
  fixed text. A preview shows the file with a sample payment.
* Each bank journal has its default layout; the file is attached to the batch and to its chatter.
* Print the payment list, or the deposit slip of a deposit, with the bank account of every payee and
  signature lines.

Bank reconciliation
===================

The module adds a Batches tab to the reconciliation screen of *Odoo 18 Reconciliation*
(``om_account_reconcile``):

* The tab lists the sent batches of the bank going in the direction of the transaction. Clicking a batch
  adds the open items of all its payments to the proposal; any of them can be removed again before
  validating, e.g. when the bank rejected one payment.
* The batch is suggested on its own when its reference is in the label of the transaction, or when its
  amount is the amount of the transaction and no other open item or batch has it.
* The automatic reconciliation reconciles a transaction with a batch whose reference is in the label and
  whose amount is the amount of the transaction.
* A payment with a journal entry is cleared by its outstanding item. A payment without journal entry (a
  payment method without an outstanding account, the default with *Odoo 18 Accounting Community*) is
  cleared with the open items of the invoices it pays, and what it pays beyond them goes to the partner;
  it is marked as paid when the transaction covers the whole batch.
* The batch is reconciled once the bank cleared every one of its payments, and back to sent when a
  reconciliation is undone.

Configuration
=============

* Accounting > Configuration > Invoicing > Bank File Layouts: copy the *Bulk Upload (CSV)* layout and set
  the columns of the template of your bank.
* On the bank journal, tab Outgoing Payments: choose the Bank File Layout.
* The bank accounts of the vendors are needed by the layouts printing an account number, a BIC or a bank
  name.
