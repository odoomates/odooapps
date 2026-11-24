========
Helpdesk
========

Helpdesk app for Odoo 20 Community: customer support tickets with teams, an
email alias per team, automatic assignment, SLA policies, a customer portal,
customer ratings and reports.

Features
========

* **Teams**: members, team leader, stages, working hours, an email alias
  (incoming emails create tickets, replies are added to the ticket), visibility
  on the portal, and a dashboard with open, unassigned, urgent and SLA failed
  tickets.
* **Assignment**: manual, to the member with the fewest open tickets, or round
  robin.
* **Tickets**: number, subject, description, customer, priority, type, tags,
  stage, status (in progress, ready, blocked), close reason, dates of opening,
  assignment, first response and closing, chatter, activities and attachments.
* **Stages**: shared between teams, closing stages, an email template sent to
  the customer when a ticket reaches the stage.
* **SLA policies**: per team, by minimum priority, ticket types, tags and
  customers; a target stage to reach within a number of working hours (team
  calendar) or calendar hours. Each ticket shows its deadline and whether the
  SLA is on time, reached or failed.
* **Customer ratings**: when the team asks for them, the customer is asked to
  rate the support when the ticket is closed.
* **Merge tickets**: messages, attachments and followers are moved to one
  ticket, the others are archived.
* **Canned responses**: the canned responses of Discuss work in the chatter of
  tickets.
* **Customer portal**: a Tickets card in My Account; the list with filters,
  sorting and search; the ticket page with its status, messages, attachments,
  a reply box, a button to close the ticket and the rating once closed.
  Customers see the tickets of their company.
* **Reports**: ticket analysis (open and closed tickets per team, time to first
  response and to close, ratings), SLA analysis (success rate) and ratings.

Related modules
===============

* **Website Helpdesk** (om_website_helpdesk): a ticket form on the website.

Usage
=====

Helpdesk > Overview shows the teams. Configure teams, stages and SLA policies in
Helpdesk > Configuration (Helpdesk administrators).

Depends
=======
[mail], [portal], [rating], [resource] addons Odoo

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
