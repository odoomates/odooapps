================
Website Helpdesk
================

A ticket form on your website for the teams of the Helpdesk app
(om_helpdesk), in Odoo 20 Community.

Features
========

* **Help page** (/helpdesk): the teams that publish a form, with their
  description. A "Help" entry is added to the website menu; remove it per
  website from the website menu editor if you do not want it.
* **Ticket form** per team (/helpdesk/<team>): name, email, phone, subject,
  description and attachments. Signed-in customers get their details filled in
  and the ticket is linked to them.
* **Customer**: found from the email, or created.
* **Confirmation page** with the ticket number and a link to follow the ticket
  in the customer portal.
* Built on the website form of Odoo: the reCAPTCHA or Turnstile modules of
  Odoo protect it when they are installed.

Configuration
=============

Helpdesk > Configuration > Teams: turn on "Website Form" on the Settings tab,
and pick a website when you have several.

Depends
=======
[om_helpdesk], [website] addons

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
