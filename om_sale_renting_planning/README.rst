==================
Rental - Planning
==================

Rent identified units (machines, vehicles, rooms) with their availability
taken from the planning.

Features
========

* Availability on the rental product: "By Quantity" (default, the behaviour
  of Rental, nothing changes for existing products) or "By Units".
* By units: the rental units are planning resources, such as maintenance
  equipment, vehicles (with Planning - Fleet), or any material resource.
* Confirming a rental books one slot per unit, from the pickup to the return,
  with the preparation time before the pickup and after the return. Free
  units are chosen automatically; the order line shows the units and lets you
  pick or change them.
* Availability and "next free date" on the quotation come from the planning:
  a unit in maintenance, on a field service job or on another rental is not
  offered twice. Confirming without enough free units is refused with the
  next free date.
* The pickup and the return move the slots; a late return extends the
  booking (hourly) and shows the clash with the next booking of the unit on
  both orders and on the Gantt.
* Moving a booking on the Gantt to another unit changes the unit of the
  order line; moving its dates changes the rental dates of the line.
* Unit Schedule: the Gantt of the units with rentals, maintenance and the
  other bookings together, also per product.
* Optional staff on the product: a role, a number of people and a duration
  create a delivery slot before the pickup and a collection slot after the
  return, with free people of the role, or open slots.

Credits
=======

Odoo Mates, odoomates@gmail.com
