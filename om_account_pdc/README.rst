==================
Post-dated Cheques
==================

This module keeps track of the post-dated cheques received from customers and issued to vendors, in Odoo 20
Community Edition, from their registration to their clearing.

Features
========

* Register a cheque received with its partner, amount, number, bank, date and the invoices it pays: the amount
  moves from the customer to the PDC Receivable account and the invoices are settled at once. A cheque issued
  does the same with the vendor bills and the PDC Payable account.
* Deposit the cheques received, to see what is waiting at the bank.
* Clear a cheque on or after its date: the amount moves from the PDC account to the bank journal. Clearing it
  before its date is refused.
* Bounce a cheque: its registration is reversed and its invoices are open again.
* Pay several invoices with one cheque, or part of one: the rest stays due.
* A daily activity on the cheques reaching their date.
* The register of the cheques received and issued, with the filters To Clear, Due and Bounced, the days left to
  their date, and the totals.
* References from their own sequences, PDC/IN and PDC/OUT, and the chatter on every cheque.

Configuration
=============

In Accounting > Configuration > Settings, Post-dated Cheques: set the PDC Receivable account (a current asset)
and the PDC Payable account (a current liability), both with reconciliation allowed, and the journal of the
registrations.

Usage
=====

Open Customers > Post-dated Cheques (or Vendors > Post-dated Cheques), create the cheque with the invoices it
pays and click Register. Deposit it, then Clear it on its date; if it bounces, click Bounce.

Credits
=======

* Odoo Mates <odoomates@gmail.com>
