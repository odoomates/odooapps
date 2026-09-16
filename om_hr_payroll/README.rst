==================
Odoo 20 HR Payroll
==================

Payroll for Odoo 20 Community Edition: salary structures and rules, employee
payslips, payslip batches and the payslip reports.

Features
========

* Compute a payslip for an employee over a period, with its worked days, its
  other inputs and one line per salary rule that applies.
* Move a payslip through Draft, Waiting, Done and Rejected, with the whole
  history and the messages kept on the payslip itself.
* Build salary structures out of salary rules, and give a structure a parent so
  that it also applies the rules of the structure above it.
* Write a salary rule as a fixed amount, as a percentage of another figure or
  as Python code, and apply it always, only inside an amount range, or on a
  Python condition.
* Group rules in categories such as Basic, Allowance, Gross, Deduction and Net,
  and use a category total inside another rule.
* Start from the rules the module installs: Basic Salary, House Rent
  Allowance, Dearness Allowance, Travel, Meal, Medical and Other Allowance,
  Gross and Net, computed from the allowance fields the module adds to the
  employment version of the employee.
* Generate the payslips of a batch for the employees you select, then confirm
  the whole batch in one step; employees belonging to another company than the
  batch are refused.
* Send a confirmed payslip to the employee by email, from the payslip or for a
  whole batch at once, with the payslip attached; the employees who have no
  work email are named back to you instead of being skipped silently.
* Print the PaySlip and the PaySlip Details PDF reports from a payslip, and the
  PaySlip Lines By Contribution Register report for a register over a period.
* Record the third parties who collect or inject money on payslips as
  contribution registers, and read back the payslip lines that belong to them.
* Refund a payslip: a credit note copy is created, computed and confirmed.
* Number confirmed payslips from the Salary Slip sequence, and take the worked
  days and the leaves from the working schedule of the employee.
* Payroll officers work on payslips, payslip lines, inputs and worked days,
  while salary structures, salary rules, salary rule categories, rule inputs
  and contract advantage templates are read-only for them and managed by
  payroll managers. Payslip batches are for payroll managers only.
* A payroll officer cannot confirm, reject or reset their own payslip; a
  payroll manager does it for them.
* In a multi-company database, payslips, payslip lines, inputs, worked days,
  batches, structures, rules and categories are limited to the companies the
  user is allowed to work in.
* A payslip can only be deleted while it is draft or rejected, and a batch only
  while it is draft.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

* Give your users their Payroll access in Settings > Users & Companies >
  Users: Officer for the people who prepare payslips, Manager for the people
  who own the salary structures and the batches.
* Review the salary rules and the salary structures in Payroll > Configuration
  > Salary Rules and Payroll > Configuration > Salary Structures. The module
  installs a set of rules you can use as they are or adapt.
* Add the third parties you pay through payslips in Payroll > Configuration >
  Contribution Registers, and point the relevant salary rules at them.
* Fill the wage and the allowances of each employee, and pick the salary
  structure, in Payroll > Employees > Contracts.
* To also post the payslips in accounting, tick Payroll Entries in Payroll >
  Configuration > Settings, which installs the payroll accounting module.

Usage
=====

* For one employee, go to Payroll > Employee Payslips, create a payslip, choose
  the employee and the period, click Compute Sheet, then confirm it.
* For a group of employees, go to Payroll > Payslips Batches, create a batch
  for the period, use Generate Payslips to pick the employees, then Mark As
  Done once the payslips are right.
* Print the payslip from the Print menu of the payslip, or send it to the
  employee with Send E-Mail on a payslip, or Send Payslips by Email on a batch.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
