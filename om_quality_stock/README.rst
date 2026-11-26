===================
Quality - Inventory
===================

Quality checks on transfers for Odoo 20 Community: receipts, deliveries and
internal transfers, blocking validation, quarantine, lots on hold, scrap,
return to vendor and a certificate of analysis.

Features
========

* **Control points on transfers**: on the operation types you choose; the
  checks are created when the transfer is confirmed, one per product line, or
  once per lot or serial number when the lots are set. Every Nth, random and
  every X days points are decided once per line.
* **Quality Checks button** on transfers, with the checks to do and the total;
  the check screen opens from it.
* **Blocking validation**: Validate opens the check screen while blocking
  checks are not passed, decided or overridden by a quality manager.
* **What to do with a failed check**: quarantine (the received goods go to the
  quarantine location of the warehouse, or an internal transfer moves them
  there), scrap, return to the vendor, retest.
* **Quarantine location** per warehouse, created at the first quarantine
  outside the stock location; the next step of a route does not take goods out
  of it.
* **Lot quality state**: OK, on hold or rejected, set by the checks (or by
  hand), with a ribbon on the lot. Lots on hold or rejected are skipped when
  Odoo reserves goods (a setting, on by default); a lot chosen by hand is
  still reserved.
* **Certificate of analysis**: a PDF per delivery with the passed checks and
  measures of the delivery and of the delivered lots.

Usage
=====

Create a control point with Where = Transfers and the operation types. Set the
quarantine location of a warehouse in Inventory > Configuration > Warehouses
(or let the first quarantine create it). The lot setting is in Quality >
Configuration > Settings.

Depends
=======
[om_quality], [stock] addons Odoo

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
