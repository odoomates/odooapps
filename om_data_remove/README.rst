===================
Odoo 20 Remove Data
===================

This module adds buttons that delete transactional data from an Odoo 20 Community database with direct
SQL statements. It is meant for a test database or for a fresh database before going live: the deletion
is immediate, committed at once and cannot be undone.

Features
========

* Delete all sales orders and their lines, and reset the sale sequences.
* Delete all purchase orders, purchase requisitions and their lines, and reset the purchase sequences.
* Delete all point of sale orders, order lines, payments and sessions, reset the POS sequences and
  recompute the ending balance of the bank statements.
* Delete all expenses and expense sheets, together with all payslips and payslip batches, and reset the
  expense sequences.
* Delete all manufacturing orders, work orders, work centre productivity and unbuild orders, and reset
  the manufacturing sequences; a separate button deletes all bills of materials and their lines.
* Delete all stock quants, moves, move lines, pickings, scraps, batches, inventories, valuation layers,
  lots, packages and procurement groups, and reset the stock, picking and warehouse sequences.
* Delete all journal entries and journal items, payments, bank statement lines, payment transactions,
  analytic accounts and analytic lines and expense sheets, and reset the accounting sequences of the
  current company.
* Reset the chart of accounts: delete all accounts, journals, taxes, tax tags, bank statements, partner
  bank accounts and journal items, and clear the account properties of the partners, product categories,
  products, stock locations and point of sale configurations.
* Delete all projects, tasks, forecasts and analytic lines.
* Delete all quality checks and alerts; a separate button deletes the quality points, alert stages,
  teams, test types, reasons and tags.
* Delete all blogs, blog posts, blog tags, wishlists, website visitors and website redirects.
* Delete all products and product templates and reset the product sequence; a separate button deletes
  all product attributes and their values.
* Delete all messages, followers and activities.
* A Remove All button runs the accounting, quality, website, inventory, purchase, manufacturing, sales,
  project, point of sale, expense, chart of accounts and message deletions one after the other.
* Recompute the complete name of the product categories and of the stock locations after a deletion.
* Every button is restricted to the users of the Settings group and asks for a confirmation before it
  runs; that confirmation is the only protection there is.
* The rows are deleted with SQL statements and committed straight away: the Odoo ORM is bypassed, so no
  delete rule, no Python constraint and no override of the models is applied and nothing is logged on
  the records.
* Documents are deleted whatever their state, posted and locked accounting entries included, and for
  every company in the database.
* A table the database refuses to empty is skipped and the error is only written to the server log,
  which can leave the database in a partly emptied state.

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

There is nothing to configure. Only the users of the Settings group see the menu, and the buttons do
nothing for anyone else.

Usage
=====

Take a backup of the database first: nothing here can be undone, and the only way back is to restore
that backup. Do not install this module on a production database.

Go to Settings > Remove Data, click the button of the data you want to delete and confirm the message.
The data is deleted and committed immediately.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>
* Sunpop.cn


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
