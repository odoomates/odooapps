==============================
WhatsApp Invoices and Payments
==============================

Invoices, credit notes and payment receipts by WhatsApp, through the Odoo
Mates WhatsApp connector (any provider it supports). Installed by itself when
Invoicing and the WhatsApp connector are both installed.

* **Send by WhatsApp** on a posted customer invoice or credit note (also from
  the list, for several at once): the composer opens with the template, the
  PDF of the invoice and the link to view and pay it online.
* **Send by WhatsApp** on a confirmed customer payment, with the payment
  receipt.
* **Automatic sending** (optional, *Invoicing > Configuration > Settings >
  WhatsApp*): each customer invoice and credit note when it is posted, each
  customer payment receipt when the payment is confirmed. Each document goes
  once: posting it again sends nothing.

The messages are WhatsApp templates you can edit or replace (*WhatsApp >
Templates*). A customer without a valid mobile number gets nothing
automatically; opted-out numbers are skipped; a problem when sending never
stops the posting and shows on the message in the chatter, to send again in one
click. With Meta, submit the templates for approval first: Meta takes only
approved templates outside the 24 hours after the customer last wrote.

License
=======

LGPL-3. Author: Odoo Mates.
