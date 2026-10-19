Sample vendor bills
===================

Bills to try the module with: upload them on *Invoicing > Vendors > Bills*
(*Upload*), or send them to the email alias of a purchase journal.

The PDFs have a text layer and are read without anything else installed. The
scans have none: they need Tesseract (``sudo apt install tesseract-ocr``),
otherwise the bill is created empty and says so.

=============================== ============================================
File                            Shows
=============================== ============================================
us_acme_office_supplies.pdf     US layout, month names, sales tax 8.5%, a PO
de_buerobedarf_mueller.pdf      German, dotted dates, 19% VAT, an IBAN
fr_papeterie_martin.pdf         French, TVA 20%, space thousands separator
in_shree_traders.pdf            Indian GSTIN, CGST 9% + SGST 9%, lakh grouping
ae_gulf_stationery.pdf          UAE TRN, VAT 5%, AED
scan_northwind_supplies.pdf     a scanned PDF (OCR), Dutch BTW number, EUR
scan_lakeside_catering.jpg      a phone photo of a bill (OCR)
=============================== ============================================

To see the vendor found, create it first with the tax number printed on the
bill (e.g. *Bürobedarf Müller GmbH*, ``DE123456789``); without it the bill
names the vendor to check. Activate EUR, INR and AED to have their bills in
their currency, and have purchase taxes of the rates printed (19%, 20%, 5%,
CGST/SGST 9%...) for the taxes and the totals to match. Posting a corrected bill teaches the vendor's profile, so its
next bill comes out right.
