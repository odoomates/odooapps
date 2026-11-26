==============================
3-Way Matching of Vendor Bills
==============================

This module matches every vendor bill line with its purchase order line and its receipts, in Odoo 20
Community Edition, and gives every vendor bill a *Release to Pay* status used to control the payments.

It depends on Purchase with Inventory (``purchase_stock``) and works with Invoicing or Accounting.

Features
========

* Per bill line linked to a purchase order line: ordered quantity, received quantity, billed quantity
  (this bill and the other posted bills of the order line, less refunds), purchase order net price and
  bill net price, and a match status: Matched, Waiting for Receipt, Quantity Exception, Price Exception or
  Not Linked.
* Release to Pay on every vendor bill:

  * Yes: every linked line is received (or ordered, for a 2-way product) at a price within the tolerance;
  * No: more is billed than received so far, or the bill has no purchase order and waits for a manual
    release;
  * Exception: more is billed than ordered, or a price is above the purchase order beyond the tolerance.

* The status is stored and follows the receipts, the posted bills and the changes of the purchase orders
  by itself; the changes are logged in the chatter of the bill.
* An accounting administrator forces Yes or No with a reason (Force Release on the bill, or Action >
  Release to Pay on a selection of bills), or sets it back to automatic; the reason is logged in the
  chatter.
* Payment control when a payment is registered for a bill not released: allow, warn (the payment window
  lists the bills) or block (the payment is refused), for one bill or several, batch payments created from
  the payment window included.
* Optional activity for the purchase representative when a posted bill is in exception.
* Views: Release to Pay column and badge, filters To Pay, Waiting and Exceptions and a group by on the
  vendor bills, a match status column on the bill lines, a 3-Way Match tab, a Receipts smart button,
  Vendors > Bills to Check, and on the purchase order a Bill Control status (billed against received) and
  a Bills to Check smart button.

Configuration
=============

Accounting > Configuration > Settings > 3-Way Matching, per company:

* 3-Way Matching: on or off (also in the Purchase settings).
* Price Tolerance (%) and Price Tolerance per Unit: the bill net price may exceed the purchase order net
  price by the larger of the two.
* Quantity Tolerance (%): on the received and the ordered quantity.
* Products Billed on Ordered Quantities: match the purchase order only (2-way), or also wait for the
  receipt (3-way).
* Bills without Purchase Order: release to pay, or wait for a manual release.
* Payment of Bills not Released: Allow, Warn or Block.
* Activity on Exceptions.

Notes
=====

* On a bill with purchase order lines, lines not linked to a purchase order (freight, for instance) are
  left out of the match.
* Down payment lines are always matched.
* Only vendor bills get a Release to Pay status; refunds are not controlled.
* The payment control applies to payments registered for the bills; a payment created on its own and
  reconciled later is not checked.

Credits
=======

Author: Odoo Mates (odoomates@gmail.com)
