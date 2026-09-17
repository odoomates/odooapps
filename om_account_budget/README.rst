=========================
Odoo 20 Budget Management
=========================

This module adds budgets to Odoo 20 Community Edition, so you can compare the
actual revenues and costs with the expected ones.

Features
========

* Create budgets with a responsible, a period and as many budget lines as you
  need.
* Follow a budget through its statuses: draft, confirmed, validated, done and
  cancelled. Only accounting managers can validate, close or cancel a budget.
* The name, the period and the lines of a budget can only be changed while it
  is in draft.
* Plan each line by budgetary position, by analytic account or by both, as an
  expense line or as a revenue line.
* Spread the planned amount evenly over the period of the line, or expect it
  in full on a planned date.
* See on every line the actual amount taken from the posted entries, the
  theoretical amount expected at today's date and the achievement percentage.
* Find the budgets and the lines that spent more than their theoretical amount
  with the Over Budget filter.
* Group the accounts in budgetary positions typed as expense or as revenue; a
  position must contain at least one account.
* Copy a budget to the next period with a wizard that proposes the following
  period of the same length.
* Split the lines of a draft budget by month or by quarter, sharing the
  planned amount according to the days of each period.
* Print a Budget vs Actual PDF from the print menu of a budget.
* Analyse the budget lines as a pivot, list or graph view.
* A daily scheduled action warns the responsible of a validated budget, with a
  message on the budget, when an expense line reaches the warning threshold of
  the company and again when it goes over its planned amount.
* Draft vendor bills that would push a budget line over its planned amount
  show a warning banner listing the lines concerned.
* When the company blocks the documents over budget, only accounting managers
  can post such a vendor bill; the other users get an explicit error.
* Follow the budget items of an analytic account from a Budget Items tab on
  its form.
* Budgets, budgetary positions and budget lines are restricted to the allowed
  companies by record rules.
* Budgets are readable by the accounting readonly group, editable by the
  accounting users and fully managed by the accounting managers.
* Demo data is installed on a demo database.

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

In Accounting > Configuration > Settings, set the percentage at which the
responsible of a budget is warned, and decide whether the documents going over
a budget are blocked for the users who are not accounting managers. Both
settings are per company.

Then create the budgetary positions you want to plan on in Accounting >
Configuration > Accounting > Budgetary Positions (Configuration > Management
when Odoo 20 Accounting (om_account_accountant) is installed), and attach the
accounts they cover.


Usage
=====

Go to Accounting > Accounting > Budgets and create a budget for the period to
plan. Add one line per budgetary position or analytic account with its planned
amount, then confirm the budget and have it validated.

While the budget runs, the actual and theoretical amounts are recomputed from
the entries, so the list and the form show where you stand. Use the print menu
for the Budget vs Actual PDF, and Accounting > Reporting > Management > Budget
Report for the pivot and graph analysis.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
