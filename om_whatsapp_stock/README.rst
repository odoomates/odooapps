===============================
WhatsApp Delivery Notifications
===============================

Delivery messages by WhatsApp, through the Odoo Mates WhatsApp connector (any
provider it supports). Installed by itself when Inventory and the WhatsApp
connector are both installed.

* **Automatic message per operation type**: *WhatsApp When Done* on an
  operation type (e.g. Delivery Orders: *Delivery: Shipped*). Each transfer of
  that type goes to its contact by WhatsApp once, when it is validated.
* **Carrier tracking**: when the carrier gives a tracking number and link (the
  shipping connectors), the message has them; the label is made before the
  message goes.
* **Send by WhatsApp** on a delivery that is ready (*Delivery: Out for
  Delivery*) or done.
* The **account** of the automatic messages is set in *Inventory >
  Configuration > Settings > Shipping*.

A contact without a valid mobile number gets nothing automatically; opted-out
numbers are skipped; a problem when sending never stops the validation.

License
=======

LGPL-3. Author: Odoo Mates.
