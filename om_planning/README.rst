========
Planning
========

Plan people, crews, equipment, vehicles and rooms on a Gantt chart, then
publish the schedule and send it to the people who do the work. The module is
built on the ``resource`` module of Odoo Community: any resource can be
planned, with or without an employee record (install *Planning - Employees*
to plan employees).

Features
========

* Resources with planning roles, a default role, a colour, a capacity (a pool
  of identical units takes several slots at once) and equipment that follows a
  person on their slots.
* Roles with a default shift template, custom slot properties and an option
  to allow overlaps.
* Shift templates (morning, evening, night...) with a short code, hours and
  break; night shifts end the next day.
* Slots with several resources, a role, start and end, break, allocated time
  in hours and percent, notes, properties and a link to any document (an
  order, a task, a ticket...). A slot without resource is an open shift.
* Draft and published slots; slots changed after their publication are
  flagged until they are published again.
* Repeating slots (every N days, weeks or months, until a date or N times);
  changes apply to this slot, this and the following ones, or the whole
  series.
* Rotations (for example 2 mornings, 2 evenings, 2 days off) applied to
  resources over a period, staggered or not, skipping their days off.
* Conflicts: overlaps (pool capacity respected), leaves and public holidays,
  time outside the working schedule, minimum rest between two days, maximum
  hours per day and per week.
* Gantt chart by resource, role or source document: load bar per row
  (planned against capacity), conflicts in red, drafts hatched, unavailable
  time greyed, an "Open Shifts" row, drag and drop between rows, copy of the
  previous period, rotations and "Publish & Send" from the toolbar.
* Calendar, list, pivot and graph views, and a "Planned vs Capacity" report
  by day, resource and role.
* Publish & Send: the slots of the period are published and each person gets
  an email with their slots, a link to their schedule page and a calendar
  feed (ICS).
* Open shifts claimed, slots switched with a colleague or left, from the
  backend, the portal or the schedule page; planning managers approve or
  refuse the requests.
* My Planning in the backend and in the portal (``/my/planning``), with the
  open shifts of the person's roles and their requests.
* Groups: Planning User (own published slots, open shifts and requests) and
  Planning Manager.

For developers
==============

The engine other modules use:

* ``resource._planning_free_intervals(start, stop)``: working time minus
  leaves minus booked slots.
* ``role._planning_find_free(start, stop, qty=1)``: free resources of a role,
  least loaded first.
* ``slot._planning_check()``: the conflicts of slots, by type.
* The ``om.planning.source`` mixin for documents that book time: slots linked
  through ``source_ref``, hours to plan and planned, ``action_plan()`` and
  ``_planning_slot_values()``.

Configuration
=============

* Planning > Configuration > Settings: rest and maximum hours rules.
* Planning > Configuration > Resources, Roles, Shift Templates, Rotations.
* Give the Planning User or Manager group to the users.

Credits
=======

Odoo Mates, odoomates@gmail.com
