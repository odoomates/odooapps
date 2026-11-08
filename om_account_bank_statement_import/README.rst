=============================
Odoo 20 Bank Statement Import
=============================

This module imports the statement files of your bank in Odoo 20 Community Edition, in the format the bank
offers: CAMT.053 (ISO 20022), MT940 (SWIFT), OFX or QFX, QIF, and CSV or Excel read through a map of the
columns of the bank.

Features
========

* CAMT.053 statements, and the camt.052 reports and camt.054 notifications, of any version of the schema.
* MT940 statements, with the structured information of the SEPA banks and the ``?20`` subfields of the
  German and Dutch banks.
* OFX and QFX files, and QIF files with the format of their dates guessed or given in the wizard.
* CSV, TSV and Excel files, read through a file map: encoding, separators, date format, rows to skip,
  sheet, and the column of the date, label, amount (or debit and credit), reference, partner, account
  number, currency, notes and identifier of each transaction.
* Foreign currency of the lines: a transaction made in another currency than the one of the account,
  such as a transfer of 500.00 EUR on a USD account, keeps its foreign amount and its currency on the
  statement line, with the sign of its amount. They are read from:

  * CSV and Excel: the foreign amount column and the foreign currency column of the file map;
  * CAMT: the instructed amount (``AmtDtls/InstdAmt``) or the transaction amount (``AmtDtls/TxAmt``) of
    the entry or of its transaction details, when its currency is not the one of the account;
  * MT940: the original amount ``/OCMT/EUR500,00/`` of the ``:61:`` or of the ``:86:``;
  * OFX: the ``CURRENCY`` or ``ORIGCURRENCY`` of a transaction, with its ``CURRATE``.

  QIF files carry no currency. A foreign amount in the currency of the journal is ignored, and an unknown
  or inactive currency stops the import with a message naming it.
* The journal is found from the bank account number of the file, a file of another account or of another
  currency is refused, and the transactions already imported are left out.
* The file stays attached to the statement, which is then reconciled as usual.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

The OFX files need the Python library ``ofxparse`` and the Excel files the library ``openpyxl``.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.


Configuration
=============

For the CSV and Excel files, create a file map in Accounting > Configuration > Bank Statement File Maps
and set it on the bank journal. For the foreign amounts of these files, fill in both the foreign amount
column and the foreign currency column of the map, and activate the currencies of your transactions.

Usage
=====

Click Import Statement on the card of the bank journal on the accounting dashboard, or in the list of the
bank statements, drop the files and import them. The journal can be left empty: it is found from the
account number of the file.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>


Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
