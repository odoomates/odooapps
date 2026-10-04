=====================
User Audit & Sessions
=====================

.. note::

   **Beta.** Reviews and feedback are welcome. Every feature is covered by
   automated tests; try it on a copy of your database first and watch how fast
   the logs grow. Report what you find at odoomates@gmail.com or on GitHub.

Who signed in, from where, and what they read, changed, exported, imported and
printed; the open sessions of every user, ended in one click.

Features
========

* **Sign-ins**: every sign-in, failed sign-in and sign-out, with the address
  and the browser. A failed sign-in is kept even though the sign-in is rolled
  back. Sign-ins through the API are marked as such.
* **Changes**: every record created, edited or deleted, with the old and the
  new value of each field that changed (``Phone: 111 → 222``). Only what really
  changed is written.
* **Reads**: one line per call of the web client or of a script (XML-RPC,
  JSON-RPC, JSON-2), with the number of records and their first ids. Odoo's own
  code reading data is never logged.
* **Exports, imports and prints**: the fields exported and the number of
  records, the rows imported, the report printed and on which record.
* **Log everything, or only what matters**: with no rule, every operation on
  every business model is logged, except a list of technical models (shown and
  editable in Settings). As soon as a rule exists, only what the rules name is
  logged: data, operations, users or groups.
* **Sessions**: every signed-in browser and device, with its address, country,
  city, first and last activity, and whether it is idle. End one session, or all
  the sessions of a user from their form.
* **Idle sessions** ended after a number of minutes without a request.
* **Sign-in emails** to the user, to the administrators or both, optionally
  only from a new device (an address and a browser not seen for 90 days).
* **Retention**: the logs are deleted after a number of days, the sign-ins
  after another (kept longer if you wish), every night, in batches.
* Logs in a list, a pivot and a graph, filtered by user, data, event and day;
  a log line opens the record it is about. *Activity* and *Sessions* buttons on
  the user form, and a **User Activity** PDF for audits.
* An API for other modules: ``env['om.user.audit.log']._om_log('refused',
  model=..., detail=...)``.

Installation
============

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

Everything is logged from the installation on. Go to User Audit >
Configuration > Settings to set how long the logs are kept, the sign-in emails
and the idle sessions, and to User Audit > Configuration > What to Log to log
only some data, operations or users.

Usage
=====

User Audit > Logs shows today's lines; remove the *Today* filter to see older
ones. User Audit > Sessions lists the open sessions, with an *End* button on
each. User Audit > Reporting > User Activity prints the activity of some users
over a period.

The logs and the sessions are visible to the Settings users only.

Limits
======

* **The superuser is never logged**, nor the code running as the superuser
  (``sudo()``): it would log Odoo's own bookkeeping. Changes made by a user,
  even through a button, are logged.
* **Reads are the most frequent event.** On a busy database, turn them off in
  Settings, or name only the data that matters in a rule.
* **The last activity of a session** is refreshed by Odoo about once an hour.
  An idle session is ended exactly on its next request; the hourly job only
  ends those idle for longer than an hour.
* **Addresses behind a reverse proxy** (nginx, a load balancer) are the proxy's
  unless Odoo runs with ``--proxy-mode``.
* **A computed field changed by Odoo** (a total following its lines) is not
  logged as an edit; the edit of the line it follows is.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
