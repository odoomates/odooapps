============================
Deferred Revenue and Expense
============================

This module spreads revenue and expense over the periods they belong to, from the invoice and bill lines,
in Odoo 20 Community Edition.

Features
========

* Put a Start Date and an End Date on a line of a customer invoice (deferred revenue) or of a vendor bill
  (deferred expense, such as a yearly insurance or rent paid in advance). The account of the line tells which
  of the two it is: only income and expense lines are deferred.
* Generate the entries on validation: when the document is posted, one entry moves the amount of its deferred
  lines out of profit and loss to the deferred account, then one entry per month end brings back the share of
  that month. The entries of past dates are posted at once, the others post themselves on their date.
* Or generate them Manually & Grouped: at the end of a period, one entry for all the deferred lines moves out
  of profit and loss what they recognise after the period, and its reversal on the first day of the next
  period brings it back.
* Choose how an amount is split: by months (each month gets the share of the month it covers), by days, or by
  full months (every month the line touches counts as a whole one). The last period takes the rounding, so the
  entries always add up to the line to the cent.
* Read the Deferred Revenue and Deferred Expense reports for any period: per account and per document, the
  total, the amount of the lines not started yet, and what is recognised before the period, in it and after
  it. Print them, and generate the grouped entries from them.
* Open the deferral entries of a document from its Deferrals button. Resetting the document to draft reverses
  its posted deferral entries and deletes the others; a credit note defers its lines the other way round.
* The analytic distribution of a line is carried to its deferral entries.

Configuration
=============

In Accounting > Configuration > Settings, Deferred Revenue and Expense: set the journal, the Deferred Expense
Account (a current asset, such as Prepaid Expenses), the Deferred Revenue Account (a current liability, such
as Deferred Income), the Amount Computation and how the entries are generated.

Usage
=====

Show the Start Date and End Date columns of the invoice lines (optional columns), fill them in on the lines
to defer and post the document. With Manually & Grouped, open Accounting > Reporting > Deferred Revenue or
Deferred Expense at the end of each period, choose the period and click Generate Entries.

Credits
=======

* Odoo Mates <odoomates@gmail.com>
