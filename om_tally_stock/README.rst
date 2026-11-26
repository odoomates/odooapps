=========================
Tally Connector Inventory
=========================

The inventory part of Import from Tally (om_tally_connector) for Odoo 20
Community.

* Units of Tally matched with the units of Odoo (Nos, Kg, Ltr...) or created.
* Stock groups (or stock categories, as you choose) become product categories;
  the other classification becomes product tags.
* Stock items matched with products by part number, name or HSN: Link, Create
  or Skip. New products get the unit, category, and in India the HSN code (with
  the Indian localization installed) and the GST taxes of their rate,
  lot tracking for batch-wise items, and the rate of Tally as cost.
* Godowns become locations of the chosen warehouse (Main Location is its stock
  location).
* The opening stock is set per godown and batch with an inventory adjustment
  dated the day before the cut-over date, at the value of Tally.
* Invoices made from vouchers get the products and units of their item lines.

Tally and TallyPrime are trademarks of their owner, Tally Solutions; this module
is not made, endorsed or supported by Tally Solutions.
