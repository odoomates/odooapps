=======================
Field Service - Sales
=======================

Time and material for field service jobs, with Sales and Timesheets.

* **Sales order of the job**: created from the job (or when the job is done),
  with a line for the service product of the job type; the travel and work
  timesheets are its delivered hours. An existing sales order item can be
  linked instead.
* **Parts**: the billable parts become lines of the order when the job is done,
  delivered by the stock moves of the job (no second delivery from the
  warehouse).
* **Invoice** from the order, like any sales order.
* **Covered jobs** (warranty, maintenance contract, goodwill): their time is not
  billed, their parts are not billed unless marked billable.
* **Travel time** billed or not, per job type.
* **Quote Follow-up**: a quotation for work found on site, linked to the job.

License
=======

LGPL-3. Author: Odoo Mates.
