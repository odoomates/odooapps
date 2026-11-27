=========================================================
AI Document Reading - Bills, Statements, Receipts and CVs
=========================================================

Read documents with your own AI provider or a local model set up in the AI
engine (``om_ai``). No key or service of Odoo Mates is used.

How documents are read
======================

* PDFs with text are read from their text (pdftotext when installed, else
  pypdf) by the chat model.
* Photos, and scanned PDFs (pages turned into images with poppler-utils), are
  read by the vision model.
* The AI answers with JSON following a schema. The answer is checked in code:
  types, dates, numbers, allowed values. It comes with a confidence and flags,
  and totals are checked (lines against the untaxed amount, balances against
  the transactions).
* Everything is shown for review. Nothing is posted or submitted
  automatically.
* Every call is logged in the AI usage, feature ``extract``, within the daily
  limits of the AI settings.

Bank statements
===============

*Accounting > Transactions > Read Statement with AI*, or *Read a statement
with AI* on a bank or cash journal of the dashboard: upload a PDF or a photo
of a statement. The transactions are listed with their date, label, partner
(found by name) and amount, with the opening and closing balances. The
wizard says what to check (balances that do not add up, another currency or
account, low confidence). Edit the lines, then **Create Statement**: the
statement and its lines are created with the file attached, ready to
reconcile.

Bridges
=======

Installed automatically with the matching app:

* **om_ai_extract_bill** (with Vendor Bill OCR): an AI engine for the vendor
  bills.
* **om_ai_extract_expense** (with Expenses): read expense receipts.
* **om_ai_extract_recruitment** (with Recruitment): read CVs into applicants.

For developers
==============

.. code-block:: python

    Extract = self.env['om.ai.extract']
    schema = Extract._schema({'total': {'type': ['number', 'null']}}, required=['total'])
    data, problems, payload = Extract._extract(raw, 'application/pdf', 'doc.pdf', schema,
                                               instructions='Read this receipt.')

Limits
======

* At most 5 pages of a PDF are read, and 3 pages of a scan.
* Scanned PDFs need poppler-utils on the server; photos do not.
* The models must support JSON output, and images for photos and scans.
* Check the readings with your own provider and model before you rely on them.

Credits
=======

Author: Odoo Mates
