=============
Field Service
=============

Field service for Odoo 20 Community: jobs at the customer site, planned on the
technicians, run from their phone and closed with a report sent to the
customer. Built on Project, Timesheets and the Odoo Mates Planning engine.

Jobs
====

* A job is a task of a project marked *Field Service*: customer, site address
  (the delivery address of the customer by default) with a directions link,
  equipment at the site, job type, priority, deadline, planned start and end,
  technicians.
* Statuses: New, Planned, Travelling, In Progress, Waiting for Parts, Done,
  Cancelled.
* Job types give the duration, a checklist template (check box, text or number
  with its unit), instructions for the technician, and can require the
  signature of the customer or a complete checklist before the job is done.
* Kanban by status, list, calendar, pivot and graph views; a job number per
  job (``JOB/00001``).

Planning and dispatch
=====================

* The job books a planning slot on the resources of its technicians: it shows
  on the Planning Gantt with the other slots, time off and conflicts.
* **Plan**: free technicians are suggested for the time asked or the first time
  they are free in the next days, nearest first (from their previous job of
  the day or their work address) and least loaded, with the conflicts of the
  choice (overlap, time off, outside working hours).
* **Dispatch** Gantt by technician or by team: the jobs to plan on the side,
  dragged onto a technician at a time, planned from their card or with the
  search button of a cell (first free time of the technician in the cell).
  Moving or resizing a slot moves the job.
* **Map** of the jobs of the day, tomorrow, the next 7 days or all open jobs
  (Leaflet with OpenStreetMap tiles), coloured by status, with the route of a
  technician in the order of their jobs and a link to open it in a maps app.
* **Optimise Routes**: the planned jobs of a technician for a day put in the
  shortest order from their work address (or the company address), with
  nearest neighbour then 2-opt on the straight-line distance, and planned one
  after the other with the travel time at an average speed. No external
  service, no API key. Jobs started, done by a crew, over several days or
  without GPS coordinates keep their time. The route opens in a maps app.
* The customer is told by email when the technician starts travelling. Hooks
  let other modules send the job planned, technician on the way and job done
  messages through a messaging app too (WhatsApp with the Field Service -
  WhatsApp module).

Technician phone screen
=======================

*Field Service > My Day*, made for a phone:

* The jobs of the day in order, other days with the arrows; **Optimise my
  day** and the route of the day in a maps app.
* One-tap navigation (geo link, Google Maps, Apple Maps, OpenStreetMap) and a
  call button.
* Start Travel, Start Work, Pause, Stop: the timers write timesheets, travel
  and work apart.
* The checklist, the work done, photos from the camera, the signature of the
  customer on the screen, Waiting for Parts and Mark as Done.
* The job report (PDF with the work done, checklist, time, parts, photos and
  signature) is emailed to the customer when the job is done.

Customers
=========

The portal shows the jobs of the customer with their status, planned date,
technicians and signed reports. The Website Field Service module adds an
online service request form.

Security
========

* **User** (technician): sees the jobs they are assigned to.
* **Manager** (dispatcher): plans every job, configures job types.

Settings
========

*Field Service > Configuration > Settings*: email the customer when the
technician is on the way, email the report when the job is done, record travel
time, average travel speed of the route optimisation.

Credits
=======

Leaflet (BSD-2-Clause, ``static/lib/leaflet/LICENSE``) draws the map. Map tiles
from OpenStreetMap, data under the Open Database License.

License
=======

LGPL-3. Author: Odoo Mates.
