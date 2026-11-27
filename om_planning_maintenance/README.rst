=======================
Planning - Maintenance
=======================

Bridge between Planning and Maintenance, installed automatically with both.

Features
========

* Every maintenance equipment gets a material planning resource, created
  automatically (also for the equipment that exists when the module is
  installed) and linked both ways. Name, company and archiving follow the
  equipment. Equipment is available around the clock unless you give its
  resource a working schedule.
* A maintenance request with a scheduled date and end books its equipment in
  the planning: one slot, linked to the request, with the Maintenance role.
* The technicians of the request are planned on the same slot as people
  (company setting "Plan Technicians"); users without a planning resource
  get one.
* Moving or resizing the slot on the Gantt moves the request; moving it to
  another equipment row changes the equipment of the request.
* A cancelled request frees the equipment, a request done before its end
  frees it from that moment.
* Conflicts: when the equipment or a technician is booked elsewhere (rental,
  field service, another slot) the request shows the conflict in red.
* Equipment Schedule: the Gantt of all bookings of the equipment, one row per
  equipment, in Maintenance and in Planning. Bookings button on the equipment.
* Equipment leaves (out of order, inspection) set on its resource make it
  unavailable; company public holidays do not.

Credits
=======

Odoo Mates, odoomates@gmail.com
