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
* Describe what your company pays besides the wage as salary components, e.g.
  Housing or Transport, and set their amount on the employment version of each
  employee. A salary rule reads a component with ``components.HOUSING``, so the
  same module serves any country without a field per allowance.
* Start from the rules the module installs: Basic Salary, Unpaid Time Off,
  Allowances, Deductions, Gross and Net. Allowances pays every component of the
  Allowance category and Deductions subtracts every component of the Deduction
  category, so a new component is paid without writing a rule; give a component
  its own rule when it has to appear on its own line of the payslip.
* Take the time off that is not paid off the payslip automatically. How much of
  a time off is paid comes from its Time Type: nothing is taken off a time off
  paid in full, the whole of an unpaid one, and half of a time off whose rate is
  50%. A closing day of the company carries no time type and is paid. The rule
  belongs to the Basic category, so the gross of the payslip is what was really
  earned in the period, and the taxes computed on it are right.
* Write your own rules against the worked days with
  ``worked_days.unpaid_ratio()``, the part of the period that is not paid, and
  ``worked_days.scheduled_days()``, the days the employee was due to work.
* Keep the rates, the thresholds and the ceilings out of the salary rules as
  rule parameters, each with its values by date. A rule reads one with
  ``parameters.SS_RATE``, and the value taken is the one of the period being
  paid, so a payslip computed again for an old period stays right. Changing a
  rate next year is entering a value in Payroll > Configuration > Rule
  Parameters, not editing the code of a rule.
* Enter the bands of a tax or of a contribution as a salary bracket instead of
  writing them in code, and compute an amount from them in one line:
  ``result = -brackets.INCOME_TAX.compute(categories.GROSS)``. A bracket holds a
  table per date, and a table per key when the same scale has one per filing
  status, per state or per pay frequency:
  ``brackets.FED_TAX.compute(base, key=employee.filing_status)``. The bands are
  applied in the way the country asks for: marginal, each band on its own slice;
  excess, the fixed amount of the band plus its rate on what exceeds its floor;
  or flat, on the whole amount.
* A rule reading a parameter or a bracket that is not configured, or that has no
  value on the date of the payslip, stops the payslip and names what is missing:
  a rate quietly worth zero would be a payslip that is wrong without saying so.
* Payroll managers own the parameters and the brackets, payroll officers read
  them: a rate is changed without giving anyone the right to write Python.
* Compute on what the employee has already been paid this year with
  ``ytd.GROSS``, the total of a salary rule over the payslips of the year
  already confirmed. Refunds are taken back, the payslips still draft do not
  count, and the year is the fiscal year of the company, so a company closing in
  March has a payroll year running April to March without anything more to set.
  The payslip being computed is not part of it: a rule needing the year
  including this period writes ``ytd.GROSS + categories.GROSS``, which says so
  and does not depend on the order the rules are computed in.
* Use it for what has to be counted over the year: a contribution stopping at a
  yearly ceiling, a tax computed on the year and spread over the periods, or a
  payslip showing its year to date.
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
* Describe what you pay besides the wage in Payroll > Configuration > Salary
  Components, e.g. a Housing component with the code ``HOUSING``. Put it in the
  Allowance category to have it paid, or in the Deduction category to have it
  subtracted.
* Fill the wage and the salary components of each employee, and pick the salary
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
