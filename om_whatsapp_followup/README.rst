===========================
WhatsApp Payment Follow-ups
===========================

WhatsApp as an action of the payment follow-up levels of the Customer Follow
Up Management of Odoo Mates, through its WhatsApp connector. Installed by
itself when both are installed.

* **Send a WhatsApp** on a follow-up level, next to the email, the letter and
  the manual action, with its WhatsApp template (*Follow-up: Payment Reminder*
  by default): the amount overdue and the overdue invoices, each with what is
  left to pay, its due date and its online payment link.
* Sent with the other actions of the level: from the **Send Reminder** dialog
  of a customer (where WhatsApp can be ticked on or off), from the batch
  sending of a plan, and by the daily **automatic follow-ups**.
* The **WhatsApp account** of a plan is set on the plan; empty, the account of
  the template or of the user is used.

Every message is kept in the chatter of the customer. A customer without a
valid mobile number gets a note in the chatter instead, opted-out numbers are
skipped, and a problem when sending never stops the follow-up.

License
=======

LGPL-3. Author: Odoo Mates.
