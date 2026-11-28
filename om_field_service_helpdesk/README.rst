==========================
Field Service - Helpdesk
==========================

Field service jobs from helpdesk tickets, for the Odoo Mates Helpdesk and Field
Service apps.

* **Plan Intervention** on a ticket: a field service job with the customer, the
  site (their delivery address), the description, the priority and the
  equipment of the ticket, in the field service project and with the job type
  of the team.
* **Automatic jobs**: a team can create a job for each new ticket, or only the
  ticket types marked *Creates a Field Service Job* do (with their own job
  type).
* **Both ways**: smart buttons from the ticket to its jobs and from the job to
  its ticket; the ticket shows the status of its job, also in the list.
* **Job done**: the ticket gets a message with the job report (PDF) and a link
  to the portal, as an internal note or as a message to the customer, and can
  be closed by itself once all its jobs are done. A *Job Report* button on the
  ticket opens the report.

Configuration
=============

*Helpdesk > Configuration > Teams*: tick *Field Service* on the team, choose
the project, the default job type, the automatic jobs, the message and the
closing of the ticket when the job is done. *Ticket Types*: *Creates a Field
Service Job* and its job type.

License
=======

LGPL-3. Author: Odoo Mates.
