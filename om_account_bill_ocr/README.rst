=======================
Odoo 20 Vendor Bill OCR
=======================

Upload a vendor bill, or receive it by email, and the draft bill is filled from it: the vendor, the bill
number, the bill and due dates, the currency, the taxes, the total and the lines of its table. Everything is
read on the server itself, with no external service and no cost.

Requirements
============

* Odoo 20.0 Community Edition, the ``account`` module.
* The PDFs with a text layer (made by an invoicing software) need nothing more. ``pdftotext`` of
  ``poppler-utils`` keeps their columns best; ``pypdf``, which Odoo ships, is used without it.
* The scans and the photos are read by Tesseract::

    sudo apt install tesseract-ocr poppler-utils
    sudo apt install tesseract-ocr-fra tesseract-ocr-deu   # a pack per language of your bills

  and the languages set in *Invoicing > Configuration > Settings > Digitization*, joined by ``+``
  (``eng+fra``).

How it reads a bill
===================

* **The vendor**: its tax number (VAT, TRN, GSTIN, USt-IdNr...), its bank account (IBAN), what its earlier
  bills taught, its email, then its name in the letterhead. The tax numbers, the bank accounts and the name
  of your own companies, printed on the bill as its customer, are never taken for the vendor.
* **The fields**: the bill number, the bill and due dates, the purchase order and the currency, from the
  labels printed next to them, in English, French, German and Spanish.
* **The amounts**: the untaxed amount, the taxes and the total, checked against each other. The purchase tax
  of the rate printed on the bill is used when the vendor has none yet.
* **The lines**: the table of the bill is read, and its lines kept only when they add up to the untaxed amount
  (quantity times price matching each amount). Otherwise the bill gets one line with its untaxed amount.
* A banner on the bill names the fields to check; the *Read, To Check* filter lists those bills. A bill is
  never posted on its own.

Electronic invoices (Factur-X, UBL, Peppol) keep being imported by Odoo from their XML: the PDF carrying one
is not read.

How it learns
=============

Posting a bill that was read teaches its vendor's profile (*Invoicing > Configuration > Invoicing >
Vendor Bill Recognition*):

* the labels the vendor prints before its bill number, its dates and its total;
* the order of its dates (day or month first), when they could be read both ways;
* the account, the taxes and the product of its bills, and whether its lines are kept;
* its tax numbers, bank accounts, email domain and letterhead, to recognize it on its next bills.

Settings
========

*Invoicing > Configuration > Settings > Digitization > Vendor Bill OCR*, per company:

* **Read**: when a bill is uploaded, on demand (the *Read the Bill* button of a draft bill), or off.
* **OCR Languages**: the Tesseract languages of the scanned bills.

Credits
=======

* Odoo Mates
