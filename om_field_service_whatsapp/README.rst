==========================
Field Service - WhatsApp
==========================

WhatsApp messages to the customer of a field service job, through the Odoo
Mates WhatsApp connector (any provider it supports). Installed by itself when
Field Service and the WhatsApp connector are both installed: neither depends
on the other.

* **Job planned**: when a job gets planned, with its date, site and technician.
* **Technician on the way**: when the technician starts travelling, with the
  link of the live tracking page.
* **Job done**: when the job is done, with the job report (PDF, for the
  providers that send files) and the link to the customer portal.

The messages are WhatsApp templates on the job that you can edit or replace
(*WhatsApp > Templates*). Each one can be turned off in *Field Service >
Configuration > Settings > WhatsApp Messages*, where the account to send from
can be chosen too. A job whose customer has no valid mobile number sends
nothing; a problem when sending never stops the job. With an account that
cannot send by itself (Click to Chat), the message waits on the job, to be sent
again from the chatter in one click.

License
=======

LGPL-3. Author: Odoo Mates.
