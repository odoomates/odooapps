====================
Tally Connector Base
====================

The engine of Import from Tally (om_tally_connector) for Odoo 20 Community: it
reads the masters and vouchers of a Tally company and keeps them in staging
tables, then shows what is in them before anything is imported.

Sources
=======

* **XML files** exported from Tally (masters from List of Accounts, vouchers
  from the Day Book), in UTF-16, UTF-8 or ASCII. The characters Tally writes that
  XML forbids (such as ``&#4;``), undeclared ``UDF:`` prefixes and lone ``&`` are
  cleaned before reading.
* **Direct connection** to the HTTP server of Tally (port 9000): the companies
  open in Tally, all the masters, the vouchers month by month, and the vouchers
  changed after an Alter ID.

Files already read are remembered: reading again takes the new files only (for
example the export of the next period), unless all are read again.

Reading in the background
=========================

For big companies, a background job reads one file (or the masters, then one
month of vouchers from Tally) per step, stages the records in chunks and commits
after each one: it goes on after the time limit of the job, shows its progress,
and can be resumed after an error. The XML is read piece by piece, so a file of
any size never sits in memory whole.

What is read
============

Company, groups, ledgers (with bill-wise opening allocations, GSTIN, address,
state, bank and tax details), voucher types, cost categories and centres,
currencies, units, stock groups, categories and items (with the opening stock
per godown and batch), godowns, and vouchers with their ledger, bill, cost
centre, bank and inventory lines.

Tally writes a debit as a negative amount: one helper (``tally_debit`` in
``tools/tally_values.py``) turns every amount into the Odoo convention.

Tally country
=============

India, United Arab Emirates, Saudi Arabia, Bahrain or other, filled from the
company of Tally (country, GSTIN or TRN) and to be checked by the user. It sets
the tax number read on the parties (GSTIN or TRN) and its checks.

Analysis
========

Counts per voucher type and financial year, the books beginning date, the
difference in opening balances, and the problems found: unbalanced vouchers,
unknown ledgers or groups, duplicate names, parties without GSTIN or TRN, tax
numbers that do not look right, bill-wise
openings that do not add up, negative stock, cancelled, optional and post-dated
vouchers left out.

A sample export of a trading company is in ``data/sample``; the "Load Sample
Files" button attaches it to an import.

Nothing has been checked against a real Tally yet: see the README of
om_tally_connector for what to check.

Tally and TallyPrime are trademarks of their owner, Tally Solutions; this module
is not made, endorsed or supported by Tally Solutions.
