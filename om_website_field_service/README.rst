=======================
Website Field Service
=======================

Online service requests and customer portal for the Odoo Mates Field Service
app.

* **Service Request** page on the website (menu and ``/field-service/request``):
  what is needed, description, equipment and serial number, up to five photos,
  preferred dates and time of day, the site (one of the addresses of a signed-in
  customer or a new one) and the contact. The request becomes a field service
  job ready to dispatch, with the photos in its chatter; the customer is found
  by email or created, a new address becomes a delivery address of the
  customer. A known serial number links the job to the equipment of the
  customer (Field Service - Stock).
* **Review**: optionally, online requests wait for a dispatcher to accept (or
  decline) them before they are offered for planning.
* **Portal**: *My Field Service* lists the jobs with their status (*Waiting for
  planning* for requests not planned yet), planned date, technicians and the
  signed report PDF, with a *Request a Service* button; the job page shows the
  request and the preferred dates.

Settings
========

*Field Service > Configuration > Settings > Online Requests*: project of the
online requests, review before dispatch.

License
=======

LGPL-3. Author: Odoo Mates.
