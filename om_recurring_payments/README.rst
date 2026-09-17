===========================
Odoo 20 Recurring Payment
===========================

This module handles payments that come back at a fixed interval, such as rents,
subscriptions or instalments, by planning them once and letting Odoo 20
Community Edition create the payments on their due date.

Features
========

* Define recurring templates holding the bank or cash journal, the interval
  (a number of days, weeks, months or years) and whether the generated payments
  stay unposted or are posted straight away.
* Confirm a template before it can be used, and set it back to draft to change
  it.
* Create a recurring payment for a partner with an amount, a currency, a start
  and an end date, a payment type of Send Money or Receive Money, and one of the
  confirmed templates.
* Generate the whole schedule with one button: a line is created for every due
  date between the start and the end date of the recurring payment.
* Give each recurring payment a reference of its own, taken from a sequence.
* Let the daily scheduled action create the payments of the lines that have
  reached their date, posting them when the template says so. A line that fails
  is logged and does not stop the following ones.
* Create the payment of a single line by hand before its date when you need to.
* Skip a line that must not be paid, and reset it to draft later if you change
  your mind.
* Stop a recurring payment: the lines that are not paid yet are skipped and no
  further payment is created for it.
* Set a recurring payment back to draft to drop its schedule, which is refused
  once one of its lines has been paid.
* Get the line due again when the payment it created is deleted, so nothing is
  lost when a payment is removed.
* Refuse a zero or negative amount, an interval that is not positive, and a
  start date later than the end date.
* Access rights for accountants and accounting managers, with multi-company
  rules on the templates, the recurring payments and their lines. A line being
  paid is locked so that the same payment cannot be created twice.

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

Create at least one template in Accounting > Configuration > Accounting >
Recurring Templates (Configuration > Management when Odoo 20 Accounting
(om_account_accountant) is installed), choose its journal, its interval and how
the payments have to be generated, then press Confirm.

The scheduled action Generate Recurring Payments runs once a day and is active
after the installation.


Usage
=====

Go to Accounting > Accounting > Recurring Payments, create
a record with the partner, the amount, the dates and the template, and press
Done to build the schedule.

Follow the lines on the form: they turn to Done as the payments are created, and
the optional Payment column shows the payment behind each line. Use Stop to end
the recurring payment before its end date.


Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
