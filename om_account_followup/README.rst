=============================
Customer Follow Up Management
=============================

This Module will add customer follow up management in Odoo 20 Community Edition

Features
========

* A Follow-ups screen listing the customers with open invoices and what to do
  today: Action Needed, Overdue (waiting for the next reminder), Promise to
  Pay or Excluded, with the reminder due, the next reminder date, the overdue
  and due amounts and the responsible, in a list or in cards.
* Send a reminder from the screen or from the customer: a dialog previews the
  email for one customer, lets you edit it, choose the recipients, attach the
  PDF of the overdue invoices and print the statement, or sends the reminders
  of several customers at once.
* The reminder emails list the overdue invoices with a link to each invoice on
  the customer portal, where the customer can download and pay it.
* A Customer Statement PDF with all the open items, the days overdue, the total
  and overdue amounts, the ageing (not due, 1-30, 31-60, 61-90 and over 90
  days) and the bank details of the company, printed from the customers.
* Several follow-up plans per company: the customers follow the default plan,
  or the plan chosen on their form, e.g. a lenient plan for key accounts. A new
  company gets a plan with a friendly reminder, a second reminder and a final
  notice.
* Set on each level the number of days after the due date, the printed
  message, whether an email is sent, whether a letter is printed and whether a
  manual action is scheduled, with its email template and responsible.
* An invoice overdue on several levels gets the reminder of the highest level
  reached.
* The manual actions are activities of the follow-up responsible of the
  customer, or of the responsible of the level; they are marked as done once
  the customer has paid everything.
* Exclude a customer from the follow-ups, with a reason.
* Record a promise to pay, with its date and amount: no reminder is sent until
  that date.
* Flag an invoice as disputed, with a reason: it is left out of the reminders,
  of the overdue amounts and of the analysis until the dispute is settled.
* Let the reminders go out by themselves: tick Send Automatically on the plan
  and the daily scheduled action sends the reminders due in the name of the
  user selected in Send As. Letters are not printed by the scheduled action.
* Send All Reminders processes the customers of a plan in one step: the levels
  are updated, the emails sent, the letters gathered in one PDF and the manual
  actions scheduled, with a summary at the end.
* The Follow-up Analysis shows, per customer, the amount due, the amount
  overdue and the level reached, in graph, pivot and list views.
* Only posted invoices are followed up; the amounts follow the active company.
* Billing users can read the follow-ups and the plans, accountants can send the
  reminders, accounting managers can create and change the plans.
* The follow-up plans and statistics are restricted to the allowed companies
  by record rules.

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

Go to Accounting > Configuration > Invoicing > Follow-up Plans. Each company
has a default plan: adapt its levels (the due days, the message to print, the
email template, and what happens at that level), or add other plans and choose
them on the customers who need them.

To send the reminders every day without any manual step, tick Send
Automatically on the plan and select the user in the Send As field.


Usage
=====

Go to Accounting > Follow-Ups > Follow-ups. The customers who need a reminder
today are listed first: open one, or select several, and click Send Reminder(s).
Print Statements prints their customer statements.

On the Payment Follow-up tab of a customer, see where the customer stands, send
a reminder, print the statement, log a call, record a promise to pay or
exclude the customer. The Disputed box of the Other Info tab of an invoice
leaves it out of the reminders.

Accounting > Follow-Ups > Send All Reminders processes all the customers of a
plan at once, and Accounting > Follow-Ups > My Follow-Ups lists the customers
you are responsible for.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
