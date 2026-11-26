=======
Quality
=======

Quality management for Odoo 20 Community: control points, inspection
templates, quality checks with measures and photos, blocking checks with a
manager override, non-conformances with corrective and preventive actions,
quality teams and a quality dashboard.

Features
========

* **Control points**: what to check (products, product categories, vendors or
  customers), where (on demand; transfers and manufacturing with the related
  modules), how often (every time, every Nth time, a random share, once per
  lot or serial number, every X days), the test, the instructions and an
  instruction file, the team and the person responsible.
* **Tests**: pass/fail, measure against a minimum, target and maximum with a
  unit and a number of samples, inspection template, photo, instructions.
* **Inspection templates**: reusable lists of parameters, each pass/fail or
  measured against limits, with their samples.
* **Quality checks**: to do, passed or failed; measures per sample, photos,
  notes, failure reason, who and when, the document they belong to, retests.
* **Check screen**: a touch-friendly window with big buttons for the shop floor
  or a tablet: pass or fail, values coloured against their limits, photos from
  the camera, a note and a failure reason, then what to do with a failed
  check. It opens from the Quality Checks button of every document.
* **Blocking checks**: a document waits until its blocking checks pass, are
  decided or are overridden by a quality manager with a reason; the reason is
  logged on the check and on the document.
* **Non-conformances**: raised by a failed check or by hand (or by email to the
  alias of a team), with stages per team, priority, product, partner, failure
  reason, root cause, cost and the linked checks.
* **Corrective and preventive actions**: containment, corrective and preventive
  actions with an owner, a due date (as an activity), a done date and an
  effectiveness check.
* **Dashboard**: checks to do and holding a document, checks done, failed and
  pass rate over 7, 30, 90 days or 12 months, by product, partner, control
  point and failure reason, non-conformances by stage and late actions.
* **Reports**: check, measure and non-conformance analysis (pivot and graph).
* **Security**: Quality User and Quality Administrator; every employee can
  record the checks of the documents they work on.

Related modules
===============

* **Quality - Inventory** (om_quality_stock): checks on receipts, deliveries
  and internal transfers, quarantine, lots on hold, certificate of analysis.
* **Quality - Manufacturing** (om_quality_mrp): checks on manufacturing orders,
  work order steps and finished lots or serial numbers.

Usage
=====

Quality > Configuration > Settings turns on the inventory and manufacturing
checks. Create control points in Quality > Quality Control > Control Points;
follow the checks and non-conformances from Quality > Overview.

Depends
=======
[product], [mail], [uom] addons Odoo

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
