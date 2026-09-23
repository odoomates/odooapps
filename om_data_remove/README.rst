===================
Odoo 20 Remove Data
===================

This module adds a Data Cleaning screen that clears every transaction of an Odoo 20 Community database
in one go, and reports what is left in each table of the database. It is meant for a test database or
for a fresh database before going live: the deletion cannot be undone.

Features
========

* One button, Clear All Transactions, deletes the transactional documents of every standard Odoo 20
  application installed on the database, and keeps the master data: partners, products, chart of
  accounts, journals, taxes, employees, bills of materials, projects and the configuration.
* Accounting and payments: journal entries and items, reconciliations, payments, bank statements and
  their lines, analytic lines and timesheets, lock date exceptions, EDI documents, payment transactions.
* Sales orders; point of sale orders, lines, payments and sessions; purchase orders and requisitions.
* Inventory: transfers, stock moves and move lines, quants, packages, lots and serial numbers, batch
  transfers, stock references and landed costs.
* Manufacturing orders, work orders, work centre time logs and unbuild orders.
* Expenses, time off and allocations, attendances and job applicants.
* CRM leads and opportunities, project tasks and updates, repairs, maintenance requests, fleet
  services, contracts and odometer logs, event registrations, survey answers, mailing traces and SMS,
  website visitors, lunch orders, loyalty cards and calendar events.
* Every message and activity of the database is deleted, on the kept records too, so the chatter starts
  empty. The followers, attachments, ratings and XML ids of the deleted documents go with them.
* The numbering of the cleared documents starts again from 1: sales, purchases, transfers and every
  operation type, lots, packages, landed costs, payments, manufacturing, point of sale.
* The screen shows, application by application, the documents and the number of records that would be
  deleted. The confirmation repeats the number and deletes nothing until DELETE has been typed.
* The deletion order is worked out by the database: a table it refuses to empty yet is tried again once
  the others are gone. A table that stays blocked, because a record that is kept still points to it, is
  named in the result with the reason given by the database.
* Everything happens in one transaction: if the request fails, nothing is deleted.
* After the clearing, and at any time from the Database Tables button, a report lists every table of
  the database with its exact number of rows, the most first, telling the transaction tables, the
  records attached to documents and the kept records apart. Only the data is listed: the tables of
  the framework and of the configuration (models, fields, views, menus, actions, access rights,
  attachments, parameters, scheduled actions, message subtypes, website, Discuss...) and the relation
  tables are counted but not shown. The full list can be searched, filtered and grouped, and its
  Framework and Relation filter shows the hidden tables.
* A table that still holds rows you do not want can be emptied from the report: Delete Rows on its
  line, or on several tables selected in the full list. It asks for DELETE, deletes the records with
  their followers, attachments and XML ids, reports a table the database refuses to empty, and shows
  the report again. The tables of the framework (ir_*, users, groups, companies, languages,
  currencies, countries) are never offered, and a relation table is emptied with the records it links.
* The rows are deleted with SQL statements: the Odoo ORM is bypassed, so no delete rule, no Python
  constraint and no override of the models is applied and nothing is logged on the records.
* The screen, the clearing and the report are reserved to the users of the Settings group.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.


Configuration
=============

There is nothing to configure. Only the users of the Settings group see the menu, and the clearing and
the report refuse anyone else.

Usage
=====

Take a backup of the database first: nothing here can be undone, and the only way back is to restore
that backup. Do not install this module on a production database.

Go to Settings > Data Cleaning, check what will be deleted, click Clear All Transactions, type DELETE in
the confirmation and click Clear All Transactions. The report of the database tables opens once the
transactions are deleted. Database Tables shows the same report without deleting anything. Click Delete
Rows on a table of the report to empty it as well.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
