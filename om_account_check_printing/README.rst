=======================
Odoo 20 Cheque Printing
=======================

This module adds configurable cheque formats to Odoo 20 Community Edition, so that vendor payments can
be printed on the cheques of any bank. Every field is placed in millimetres on the page.

Features
========

* Define as many cheque formats as you need, each with its paper size: A4, US Letter or a custom size
  such as a cheque leaf of a cheque book.
* Place the date, payee, amount in figures, amount in words, memo, cheque number, company name and any
  fixed text of your own at an exact position in millimetres from the top left corner of the page.
* Set the width, height, font size, bold, alignment, line spacing, letter spacing, rotation and border
  of every printed field; letter spacing fills date boxes and rotation prints an A/C payee crossing.
* Two horizontal and vertical offsets move the whole layout to correct the alignment of your printer,
  without touching the position of each field.
* Choose the date format printed on the cheque: the format of the language, or one of DD/MM/YYYY,
  MM/DD/YYYY, YYYY-MM-DD, DD-MM-YYYY, DDMMYYYY or DD Mon YYYY.
* The amount in figures can be printed with the currency symbol and surrounded by stars so that nothing
  can be added to it.
* The amount in words can be printed in capitals, followed by a suffix such as "Only", and the rest of
  the line filled with stars.
* Optionally print one or two payment stubs under the cheque, listing the bills paid by the payment with
  their due date, number, original amount, balance due and amount paid.
* When the stub spills over several pages, the cheque is printed on the first page and the next pages
  carry VOID in place of the amounts.
* A Test Print button prints the format with sample values on plain paper, to hold against a real cheque
  and adjust the positions.
* Each cheque format keeps its own paper format without margins, created and updated automatically, so
  the printed positions match the measurements.
* A cheque format can be shared by all companies or limited to one; users only see the formats of their
  companies.
* Each bank journal points to the cheque format of its cheque book; when none is set, the first format
  available for the company is used.
* Two cheque formats are installed as examples: a cheque on the top of an A4 page with two stubs, and a
  202 x 92 mm cheque leaf.
* Accounting advisers can create and change the cheque formats; other accounting users can read them.

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

Set the cheque layout to "Configurable Cheque Format" on the company, or on the bank journal in
Accounting > Configuration > Accounting > Journals, on the tab where the cheque printing options of the
standard Check Printing module are.

Then go to Accounting > Configuration > Accounting > Cheque Formats, start from one of the two formats
installed or create your own, place the fields, print a test and adjust the positions and the offsets
until they match your cheques. Choose the format on the bank journal that uses that cheque book.

Usage
=====

Register a vendor payment on the bank journal with the Checks payment method, then print it as usual.
The cheque is printed with the format of the journal. When no cheque format is available, a message
takes you to the cheque formats to create one.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
