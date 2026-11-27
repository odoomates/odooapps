=====================
WhatsApp POS Receipts
=====================

The Point of Sale receipt by WhatsApp, through the Odoo Mates WhatsApp
connector. Installed by itself when the Point of Sale and the WhatsApp
connector are both installed.

* **WhatsApp Receipts** in the settings of a point of sale, with the template
  (*Point of Sale: Receipt*) and the account to send from.
* In the **send receipt** dialog of the POS, a phone number (filled with the
  number of the customer) and a WhatsApp button next to the email.
* The customer gets the receipt as a picture, and the invoice PDF when the
  order is invoiced, with the providers that send files. With Click to Chat,
  WhatsApp opens in a new tab with the text filled in.
* With the Meta Cloud API, the receipt goes as a PDF at the top of the
  approved template (the invoice pages follow when the order is invoiced),
  so it reaches customers who have not written in the last 24 hours. Submit
  the template to Meta once from *WhatsApp > Templates*.

As for the email receipt, the order must be synced with the server: an order
still waiting offline asks to sync first. The message is kept on the order;
opted-out numbers are skipped, and the cashier sees why a receipt could not go.

License
=======

LGPL-3. Author: Odoo Mates.
