===============================
Field Service - Subscriptions
===============================

Maintenance contracts for field service, sold with the Odoo Mates
Subscriptions app.

* **Maintenance products**: a subscription product with *Maintenance Visits*
  creates the field service jobs of its visits: every N periods of the
  recurring plan, a number of days before the visit is due, with a job type
  (duration, checklist, instructions) and a preferred technician.
* **Subscription**: the next visit on each maintenance line, a preferred
  technician for the contract, the jobs of the contract behind a smart button,
  *Create Due Visits* to create them now. A scheduled action creates them
  every day while the subscription runs (not when paused or closed, not past
  its end date).
* **Coverage**, per product: the visits of the contract are covered, or every
  job of the customer is covered while the contract runs (repairs too), or
  nothing is covered. A covered job is not invoiced as time and material: its
  timesheets are not billed and its parts are not billed unless marked
  billable (Field Service - Sales). Jobs created for a customer with an
  all-covering contract are linked to it by themselves.

License
=======

LGPL-3. Author: Odoo Mates.
