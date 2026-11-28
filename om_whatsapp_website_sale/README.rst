=============================================
WhatsApp eCommerce Orders and Abandoned Carts
=============================================

Bridge between eCommerce and WhatsApp Quotations and Orders, installed by
itself when both are installed.

* **Online order confirmation**: *Website > Configuration > Settings > Order
  Confirmation > WhatsApp*. An order of the website goes to the customer by
  WhatsApp once, when its payment confirms it (*eCommerce: Order Confirmed*).
  Empty, the order confirmation of Sales applies when it is sent automatically.
* **Abandoned cart reminder**: *Follow up abandoned carts > WhatsApp*. A cart
  left by a signed-in customer gets one WhatsApp reminder, after the delay of
  the abandoned carts, with its products and the link back to the cart
  (*eCommerce: Abandoned Cart*). As with the email reminder, a cart with a
  failed payment, free, out of stock or followed by an order gets none; only
  the carts left after the reminder was turned on are reminded.

A scheduled action checks the carts every hour. Each cart is reminded once;
opted-out numbers get nothing.

License
=======

LGPL-3. Author: Odoo Mates.
