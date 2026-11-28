===============================================
WhatsApp AI Sales Assistant - Shipping Messages
===============================================

Bridge between the WhatsApp AI Sales Assistant (``om_ai_whatsapp``) and the
deliveries of the inventory (``stock_delivery``). It installs by itself when
both are installed.

Features
========

* When a delivery of an order that came from a WhatsApp AI conversation is
  validated, the customer gets a WhatsApp message in that conversation with
  the carrier and the tracking link (or the tracking reference when the
  carrier has no tracking link).
* Once per delivery: a backorder sends its own message when it is validated.
* Works with the carrier connectors that fill the tracking reference of the
  delivery, such as the Odoo Mates delivery connectors.
* A number that opted out (STOP) gets nothing; the delivery says why in its
  chatter. When a person has taken over the conversation the message is still
  sent, as a notice, and a note says so in the conversation.
* Per WhatsApp account: *Shipping Messages* on or off (on by default) and the
  text of the message, translatable, with ``{order}``, ``{delivery}``,
  ``{carrier}`` and ``{tracking}``.
* The order status the assistant gives shows the carrier and the tracking
  link of each delivery.
* A message that cannot be sent never blocks the validation of the delivery.

Author
======

Odoo Mates
