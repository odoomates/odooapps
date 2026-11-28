=================
Planning - Fleet
=================

Bridge between Planning and Fleet, installed automatically with both.

Features
========

* Every vehicle gets a material planning resource, created automatically
  (also for the vehicles that exist when the module is installed) and linked
  both ways. Its name follows the vehicle (plate, brand, model).
* A vehicle with a driver follows the driver: it is added to the slots of the
  driver, and the coming slots move to the new driver when the driver
  changes. The driver is found from their user or their employee; an internal
  user without planning resource gets one.
* "Follows the Driver" per vehicle, with a company default in the planning
  settings. Pool vehicles without the option are booked on their own.
* Vehicle bookings and conflicts: a vehicle cannot be booked twice at the same
  time without a red conflict.
* Vehicle Schedule: the Gantt of the bookings, one row per vehicle, in Fleet
  and in Planning. Bookings button on the vehicle.

Credits
=======

Odoo Mates, odoomates@gmail.com
