==================================
Odoo2XL - Odoo Excel Reports
==================================

Adds Excel export to the Odoo **Print** flow. Any PDF report can be exported as a real
spreadsheet, not a picture of the PDF. The export is generated on the server: no browser
extension is needed and nothing leaves your Odoo server.

Features
========

* **Print chooser:** printing a PDF report (Print menu, Print buttons, wizard reports) first
  asks *PDF / Excel / Both / Preview* in a popup ("Choose the format. Esc cancels.").
* **Preview:** the *Preview* button opens the PDF in a new browser tab. The tab is served
  inline under the report's real file name (its "Printed Report Name", for example
  ``Quotation - CQ/08/0009.pdf``), so the PDF viewer's download keeps that name instead of
  an id. Downloads (PDF and Excel) use the same naming. If the browser blocks pop-ups, a
  warning is shown and the PDF is downloaded instead.
* Amounts, quantities (with units), percentages and dates are exported as real Excel values;
  codes and references (leading zeros, VAT, IBAN...) stay text.
* Bold totals, indentation, frozen header row, filters on the main table and sensible column
  widths.
* Several records printed at once give one sheet per document, plus an **All lines** sheet
  (pivot-friendly) when they share the same table layout.
* Report filters (dates, journals, target moves) are kept above the table.
* Print-ready: landscape, all columns fit the page width.
* The header and footer repeated by the report layout are dropped.

Configuration
=============

* **Chooser:** set the system parameter ``om_excel_reports.ask_format`` to ``0`` to turn off the
  PDF / Excel / Both popup for everyone. Printing then always gives the PDF, and the Excel export
  is no longer offered in the interface.
* **Reports with their own Excel export:** if a module (for example one built on ``report_xlsx``)
  already provides an ``xlsx`` report action on the same model as a PDF report, the popup is not
  shown for that report, so users do not get two Excel versions of it.

Access follows the normal report access of the user: the Excel file is generated from the
same HTML that the report renders.

Technical notes
===============

* The module does not change any ``ir.actions.report`` record or field; it only adds the
  ``_render_excel`` method, the routes and the web client dialog.
* Routes: ``/report/excel/<report_name>[/<ids>]`` (download through ``/report/download``, type
  ``excel``) and ``/om_excel_reports/preview/<report_name>[/<ids>]`` (inline PDF with its file
  name).
* Converter: ``lib/html_to_xlsx.py`` (lxml and xlsxwriter, no Odoo dependency, unit-testable).
* All ``qweb-pdf*`` report types can be exported.
* Python dependencies: ``xlsxwriter`` and ``lxml``.

Limitations
===========

* Images, logos and barcodes are skipped.
* Reports without tables are exported as plain text rows.
* Number and date recognition uses the user's language settings (decimal and thousands
  separators, date format).

Tests
=====

::

    odoo-bin -d <db> -i web_tour,om_excel_reports --test-enable --test-tags=/om_excel_reports

``web_tour`` is only needed for the browser tours. Converter-only tests: use
``--test-tags=/om_excel_reports:TestParsing,/om_excel_reports:TestInvoice``.

Credits
=======

Server-side version of the Odoo2XL browser extension by Odoo Mates
(https://github.com/odoomates/odoo2xl): the same conversion rules, re-implemented in Python so
the export runs inside Odoo.

Odoo2XL is not affiliated with or endorsed by Odoo S.A.

Contributors
------------

Akshay Manoj

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates <odoomates@gmail.com>

License
=======

LGPL-3
