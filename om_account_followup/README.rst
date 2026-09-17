=============================
Customer Follow Up Management
=============================

This Module will add customer follow up management in Odoo 20 Community Edition

Features
========

* Define one follow-up plan per company, with as many follow-up levels as you
  need.
* Set on each level the number of days after the due date, the printed
  message, whether an email is sent, whether a letter is printed and whether a
  manual action is assigned.
* Choose the email template and the responsible user assigned by a level.
* Process the overdue customers in one step: the follow-up level of the
  unreconciled receivable items is updated, the emails are sent, the letters
  are gathered in one PDF and the manual actions are assigned.
* Get a summary at the end of the processing with the number of emails sent,
  the addresses that were missing, the letters to print and the manual actions
  per responsible.
* Let the follow-ups run by themselves: tick Send Automatically Every Month on
  the plan and the monthly scheduled action processes it in the name of the
  user selected in Send As. Letters are not printed by the scheduled action.
* Follow the overdue amounts on the customer form, in a Payment Follow-up tab
  showing the unreconciled entries, the latest follow-up level and date, the
  next action, its date and its responsible.
* Print the overdue payments report or send the overdue email for one customer
  from the buttons of that tab, and clear the next action with Mark as Done.
* Browse the customers to remind with the filters on overdue credits,
  follow-ups to do, unassigned customers and your own follow-ups.
* See and set the follow-up level and the follow-up date on the journal items.
* Print the Follow-up Report PDF for the selected customers.
* A message is posted on the customer when a letter is going to be sent and
  when a user becomes responsible for the next action.
* The follow-up plans and the follow-up statistics are restricted to the
  allowed companies by record rules.
* Billing users can read the follow-up levels, accounting managers can create
  and change them.
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

Go to Accounting > Configuration > Invoicing > Follow-up Levels and define the
levels of the plan of your company: the due days, the message to print, and
what has to happen at that level (email, letter, manual action).

Only one plan per company is allowed.

If you want the follow-ups to be processed every month without any manual
step, tick Send Automatically Every Month on the plan and select the user in
the Send As field.


Usage
=====

Go to Accounting > Follow-Ups > Send Letters and Emails, check the sending
date, select the customers to remind and process them. The summary screen
shows what was done and lets you print the letters.

Accounting > Follow-Ups > Do Manual Follow-Ups lists the customers with
overdue credits, and Accounting > Follow-Ups > My Follow-Ups lists the ones you
are responsible for.

A single customer can also be followed up from the Payment Follow-up tab of
its form.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
