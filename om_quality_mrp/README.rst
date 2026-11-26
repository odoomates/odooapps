=======================
Quality - Manufacturing
=======================

Quality checks in manufacturing for Odoo 20 Community: per manufacturing order,
per work order step and per finished lot or serial number, blocking Produce
until they pass, scrap or rework from a failed check.

Features
========

* **Control points on manufacturing orders**: for products, categories and
  manufacturing operation types; one check per order, or one per finished lot
  or serial number (created at Produce, when the serial numbers are known).
* **Control points on work order steps**: for operations or work centres; the
  checks are created with the work orders of the order.
* **Quality Checks button** on manufacturing orders and work orders, and a
  button on each work order line of the order.
* **Blocking**: Produce opens the check screen while blocking checks wait, and
  a work order cannot be finished before its own blocking checks pass, unless
  a quality manager overrides them with a reason.
* **Failed checks**: rework (an activity on the order and a new check for the
  reworked goods), scrap, retest; the non-conformance knows the order, the
  work order and the work centre; the finished lot goes on hold.

Usage
=====

Create a control point with Where = Manufacturing Orders or Work Order Steps.
Work order steps need the Work Orders setting of Manufacturing.

Depends
=======
[om_quality_stock], [mrp] addons Odoo

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
