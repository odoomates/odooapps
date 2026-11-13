=============================
Odoo 20 Accounting Automation
=============================

This module adds ready-made accounting workflows to the templates of
Automation Studio, for Odoo 20 Community Edition. Start one from
*Automation Studio > New > From a template*, check it in the designer and
publish it: nothing runs before.

Templates
=========

* **Bills: Due Soon** - three days before the due date of a posted vendor bill
  not paid yet, an activity to pay it.
* **Bills: Left in Draft** - a vendor bill still in draft three days after it
  was created, an activity to check and post it.
* **Bills: Posted Without Vendor Reference** - a note and an activity to add
  the reference of the vendor, so that the duplicates are found.
* **Invoices: Posted but Not Sent** - a customer invoice not sent the day after
  it was posted, an activity for the salesperson to send it.
* **Invoices: Large Amount Posted** - a customer invoice of 10,000 or more, an
  activity for the accounting manager to follow its payment.
* **Payments: Left in Draft** - a payment still in draft two days after it was
  created, an activity to confirm or cancel it.
* **Post-dated Cheques: Maturing** and **Bounced**, once Post-dated Cheques is
  installed - an activity to deposit a received cheque the day before its date;
  a call to the partner of a bounced cheque, then an activity for the manager
  three days later when still not settled.

The templates are shared by every company. Each is added once: a template
deleted does not come back. The overdue reminders of the customer invoices are
left to Customer Follow-ups, and the approvals to the Approvals app.
