============
File Layouts
============

Design the files you send out of Odoo, column by column, and export them from
the Action menu of the records: the salary transfer file of a bank, a
declaration to an office, a list for a partner.

Features
========

* CSV (separator and quotes of your choice), fixed width, or Excel.
* A header written once, one line per record, and a footer written once, e.g.
  the number of lines and their total. The CSV and Excel files can start with
  a row of the column titles.
* Each column is a Python expression of the record, e.g. ``record.name``, with
  its type and how it is written: width, alignment, padding, upper case,
  decimals and decimal separator, implied decimals (1500.00 as ``150000``),
  date format. The expressions also read ``today``, ``now``, ``count``,
  ``total``, ``company`` and ``user``.
* Encoding (UTF-8, UTF-8 with BOM, Windows-1252, ASCII) and line ending, and the
  file name, e.g. ``SALARY_{date}``, with ``{layout}``, ``{date}``,
  ``{datetime}`` and ``{company}`` replaced.
* Each layout appears in the Action menu of its model, as Export: followed by
  its name. The export shows a preview of the file and its problems, e.g. an
  empty required value or a value longer than its column, before you download
  it.
* Every file exported is kept, with who exported it, when and for which
  records, to download it again as it was sent and to open its records. Each
  user reads the files they exported; the administrators read them all.
* A layout belongs to one company or is shared by all of them.
* Another module may give the lines of the file itself, as Payroll Bank Files
  does with the salary transfers of the payslips.

Configuration
=============

The File Layouts administrators (Settings > Users & Companies > Users, File
Layouts: Administrator) design the layouts in Settings > Technical > File
Layouts > File Layouts, with the developer mode. The other users can read the
layouts and export with them.

Usage
=====

#. Create a layout in Settings > Technical > File Layouts > File Layouts: the
   model it applies to, the format and the file name, then the columns of the
   Lines tab, and of the Header and Footer tabs if the file needs them.
#. Select the records in their list view, open the Action menu and choose
   Export: followed by the name of the layout.
#. Check the preview and the problems, then click Download.
#. Find every file exported in Settings > Technical > File Layouts > Exports,
   or from the Exports button of the layout.

Dependencies
============

* Discuss (``mail``)

Support
=======

Odoo Mates, odoomates@gmail.com
