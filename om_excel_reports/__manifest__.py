# Part of Odoo2XL - Odoo Excel Reports (om_excel_reports). License: LGPL-3.
{
    'name': 'Odoo2XL - Odoo Excel Reports',
    'version': '1.0.1',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'category': 'Productivity',
    'summary': 'Excel Reports, Export PDF Report to Excel, XLSX Report, Print Report in Excel, '
               'Report to Spreadsheet, Odoo2XL, Excel Export of Any Report',
    'description': """
Odoo2XL - Odoo Excel Reports
============================
Adds Excel export to the Odoo Print flow. Any PDF report can be exported, and
the result is a real spreadsheet - not a picture of the PDF.

* Works for every PDF report: invoices, quotations, delivery slips and any
  other report, including custom and third-party ones - no per-report code.
* PDF / Excel / Both / Preview chooser when printing, including wizard reports.
* Reports that already have their own Excel export (an xlsx report action on the
  same model) keep it: the chooser is not shown for them.
* Amounts are numbers with currency formatting, dates are real Excel dates,
  account codes and references stay text.
* Quantities keep their unit and still sum.
* Bold totals, indented account levels, frozen header row and filters on the
  main table.
* Report filters (dates, journals, target moves) are kept above the table.
* Several records: one sheet per document, plus an "All lines" sheet with a
  Document column for pivot tables.
* Files are named after the record reference or the report name.
* Print-ready: all columns fit the page width (landscape).
* Generated on the server, inside Odoo - no browser extension and no data
  leaves your system.

Limitations: images, logos and barcodes are skipped; reports without tables
are exported as text rows.

Server-side version of the Odoo2XL browser extension by Odoo Mates.
Not affiliated with or endorsed by Odoo S.A.
""",
    'license': 'LGPL-3',
    'depends': ['web'],
    'external_dependencies': {'python': ['xlsxwriter', 'lxml']},
    'assets': {
        'web.assets_backend': [
            'om_excel_reports/static/src/js/*.js',
            'om_excel_reports/static/src/xml/*.xml',
            'om_excel_reports/static/src/scss/*.scss',
        ],
        'web.assets_tests': [
            'om_excel_reports/static/tests/tours/*.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
}
