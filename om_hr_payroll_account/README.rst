=============================
Odoo 20 HR Payroll Accounting
=============================

This module connects the Odoo 20 Community payroll to the accounting: each confirmed payslip posts a
journal entry built from the debit and credit accounts of the salary rules.

Features
========

* Each salary rule gets a Debit Account, a Credit Account, an Analytic Account and a Tax on an
  Accounting tab.
* Each payslip gets a Salary Journal, an accounting date and a link to the journal entry it created.
* The salary journal of a payslip defaults to the first miscellaneous journal of the company of the
  payslip; the journal set on the employee contract is used when there is one.
* The accounting date of the payslip can be left empty, in which case the end date of the period is
  used.
* Confirming a payslip creates the journal entry and posts it: one debit and one credit line per salary
  rule category line, with the analytic distribution and the tax of the rule.
* The partner of a journal item is taken from the contribution register of the salary rule, and is also
  set when the account of the rule is a receivable or payable account.
* When the debits and the credits do not match, an adjustment line is added on the default account of
  the salary journal; the entry is refused when that journal has no default account.
* Confirming a payslip whose salary rules have no debit and credit account is refused with a message.
* A refund payslip posts the opposite entry, so the books follow the cancellation.
* Cancelling a payslip deletes its journal entry, after a confirmation on the button.
* When the journal entry cannot be deleted, for instance because it falls inside a lock date, the
  cancellation is refused with a message asking to reverse the entry in Accounting first.
* When the entry has already been reversed by a posted reversal, cancelling the payslip leaves the entry
  and its reversal in the books.
* The salary journal of a payslip must belong to the company of the payslip; the entry is created in
  that company.
* Payslip batches get their own Salary Journal, shown in the list, the form and the filters of the
  batches, and the payslips generated from a batch take the journal of the batch.
* Payroll officers can confirm payslips without any accounting rights: the entry is created with the
  configuration of the salary rules, and they are given read access on the journals, accounts and taxes.
* Employee contracts get an Analytic Account and a Salary Journal, used by the payslips of the employee.

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

Set the debit and credit accounts of the salary rules in Payroll > Configuration > Salary Rules, on the
Accounting tab of each rule. The analytic account and the tax of the rule are optional.

Make sure the company has a miscellaneous journal with a default account, so that the payslips have a
salary journal and the adjustment line can be posted. A different journal can be set on the employee
contract, on the payslip or on the payslip batch.

Usage
=====

Create a payslip in Payroll > Employee Payslips, or a batch in Payroll > Payslips Batches and generate
the payslips of the employees. Check the salary journal and the accounting date, compute the payslip and
confirm it: the journal entry is created and posted, and is available from the payslip.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>
* Odoo SA


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
