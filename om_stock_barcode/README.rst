==============================
Barcode Scanning for Inventory
==============================

A touch screen for the warehouse floor in Odoo 20 Community: process receipts,
deliveries and internal transfers, count stock and look up any barcode with a
phone, a tablet or a handheld scanner. Built on the Inventory app: the same
transfers, lots, serial numbers, packages and locations, with no new documents
to learn.

Transfers
=========

* Scan an operation type to see its transfers, or a transfer reference to open
  it; a search finds the others.
* Lines grouped by location, the scanned and the planned quantity on each, in
  colour: to do, started, done, more than planned.
* Scan in order: source location, product, lot or serial number, package,
  destination location. Each scan adds one; the +/- buttons and a tap on the
  quantity change it by hand. Packaging barcodes add the packaging quantity.
* Lots and serial numbers are asked for tracked products. A serial number is
  scanned once per transfer, must be in stock (not already in stock for
  receipts) and in the scanned location. Another lot or location than the
  reserved one is taken when it is there.
* Scan a full package to take it as a whole; scan an empty package, or tap the
  package button, to pack the scanned products.
* Products that are not in the transfer can be added by scanning them (an
  option per operation type), or by typing their name.
* Validate with the backorder question of Inventory, for what was not scanned.
* Clear messages for wrong scans: not in this transfer, not in this location,
  lot or serial number needed, serial number already scanned, unknown barcode.
* A colour flash, a sound and a vibration for each scan: one for a good scan,
  another for a question, another for an error.

Scanning
========

* Handheld and Bluetooth scanners that type the barcode (keyboard mode).
* The camera of phones and tablets: the barcode reader of the browser where
  there is one, otherwise the reader that comes with Odoo.
* GS1 barcodes read with the GS1 nomenclature of Odoo: product (GTIN), lot or
  serial number, expiration date and quantity in one scan.
* Any barcode can also be typed.

Inventory count
===============

* Scan the location to count (the locations with a count due or started are
  listed), then the products and their lots; scan a shelf or a package inside
  it to count there.
* The counted and the recorded quantity side by side, with the difference.
* Apply: the inventory adjustment of Inventory, with its conflict check.

Lookup
======

* Scan a product for its stock by location, a lot or serial number for where it
  is and its history, a location or a package for its contents.

Settings
========

* Per operation type (Inventory > Configuration > Operation Types, Barcode App):
  scan the source location first, scan the destination location, put the
  products in a package, allow unplanned products.
* Per company (Inventory > Configuration > Settings, Barcode): sounds and
  vibration, camera button.

Usage
=====

Open the Barcode app. Inventory users can use it; the rights of Inventory
apply to every scan.

Credits
=======

Odoo Mates, odoomates@gmail.com
