=========================
Field Service - Quality
=========================

Quality worksheets on field service jobs, with the Odoo Mates Quality app.
Installed by itself when Field Service and Quality are both installed.

* **Control points for jobs**: a quality control point of type *Field Service
  Jobs* applies to the jobs of its job types: pass or fail, a measure with its
  tolerance, a photo, an inspection template, instructions and a failure
  message. They are listed on the job type too.
* **On the phone**: the technician sees the checks of the job on the phone
  screen and records them on the quality check screen (pass/fail buttons,
  values against their limits, photos, notes).
* **Failures**: a failed check raises a non-conformance (when its point asks
  for it) linked to the job, the customer and the equipment at the site.
* **Job report**: the checks, their values, photos and results are printed in
  the job report PDF.
* **Done only when checked**: a job cannot be marked as done while one of its
  checks is still to do (setting *Quality Checks Required*); blocking points
  hold the job until their check passes or a quality manager overrides it.

Configuration
=============

*Field Service > Configuration > Quality Control Points*, or the *Quality
Checks* tab of a job type. *Settings > Field Service > Quality*. The
non-conformances of the jobs are under *Field Service > Reporting*.

License
=======

LGPL-3. Author: Odoo Mates.
