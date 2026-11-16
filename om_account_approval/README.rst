============================
Odoo 20 Accounting Approvals
============================

This module makes the approval flows of the Approvals app hold for the
accounting of Odoo 20 Community Edition: a vendor bill, credit note, journal
entry or payment waiting for its approval is not posted, whatever posts it.

Features
========

* Applies the flows set on the Post button of the journal entries and on the
  Confirm button of the payments to every way of posting them: the Post action
  of the lists, the Confirm Entries wizard, the auto-post of the scheduled
  entries, the Register Payment wizard and the recurring payments.
* Uses an approved request up with the first post, whatever posts the record:
  reset to draft, the record asks again.
* Leaves aside, in the auto-post, the entries waiting for an approval, so that
  they do not hold the others back; asks for their approval, and stops
  auto-posting them once the approval is refused or withdrawn.
* Never stops the entries Odoo posts itself: payments, bank statements, cash
  basis taxes, exchange differences, cancelling reversals and depreciation.
* Adds Post Without Approval on the journals, for the journals of the entries
  posted by Odoo, e.g. currency revaluation or year-end closing.
* Adds a Waiting for Approval filter on the invoices, bills, journal entries
  and payments.
* Adds templates to the gallery of the Approvals app: customer invoices above
  an amount, credit notes, manual journal entries, and the vendor payments next
  to the vendor bills.
* Installs itself as soon as Accounting and Approvals are both installed.

Configuration
=============

In Approvals, create a flow from the gallery, e.g. *Approval above an amount*
for the vendor bills, check it and activate it. Tick *Post Without Approval* on
the journals whose entries are posted by Odoo itself when a flow applies to
their entries, e.g. a flow on the manual journal entries.
