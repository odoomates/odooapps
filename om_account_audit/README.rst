========================
Odoo 20 Accounting Audit
========================

This module brings the inalterability features of Odoo 20 Community within
reach of the accountants and auditors, and keeps the evidence of the checks.

Features
========

* Adds an Audit menu under Review: Integrity Checks, the Data Inalterability
  Report and Secure Entries of Odoo (otherwise without a menu, or only in
  debug mode), the posted Entries Not Secured, the Audit Trail and the Audit
  Pack.
* Keeps every data inalterability check in a history: the hash chain of each
  journal recomputed, the first and last entries secured, and the entries
  found changed since they were secured.
* Runs the check every week; a check finding changed entries asks the
  accounting administrators to look at it.
* Adds two checks to the period closing checklist: the posted entries not
  secured yet, and, blocking the closing, a last check finding changed entries.
* Secures the posted entries of a period when it is closed, when the company
  asks for it (off by default: secured entries can never be changed again).
* Secures the sales, purchase and miscellaneous journals in one click from the
  settings, after a confirmation.
* Prints an Audit Pack for a period: the result of the integrity check, the
  entries posted, secured, not secured and in draft, the lock dates and the
  period closings, the changes logged on the journal entries, and the users
  with an accounting access.

Configuration
=============

Accounting > Configuration > Settings > Inalterability: the weekly check, the
securing of the entries on closing, and the securing of the journals.
