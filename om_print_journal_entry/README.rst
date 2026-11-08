=====================
Print Journal Entries
=====================

Print any journal entry, invoice or bill as a PDF.

Open a journal entry, an invoice, a bill or a payment entry and click
**Print > Journal Entries** (in the action menu from Odoo 17), or select several
entries in the list and print them together. The PDF, on the company letterhead, shows:

* what the entry is (journal entry, customer invoice, vendor bill...), its
  number and a status badge;
* the journal, accounting date, invoice and due dates, partner, reference and
  source document;
* every line: account, partner, label, analytic distribution, taxes, debit and
  credit, and the amount in currency for an entry in another currency;
* the totals of debit and credit;
* a tax summary: the base and the amount of each tax.

Columns that would be empty are left out.

This print used to be part of Accounting PDF Reports (``accounting_pdf_reports``),
which now depends on this module: on a database where it is installed, the
report is handed over with what the users changed on it.

Credits
=======

Odoo Mates, odoomates@gmail.com
