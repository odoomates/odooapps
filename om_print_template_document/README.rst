==========================
Print Templates: Documents
==========================

Files the prints of a template as documents of the record printed, with their
PDF and an expiry date, e.g. a No Objection Certificate valid for 30 days that
shows on the documents of the employee and is reminded before it expires.

Features
========

* A Filing tab on the print templates: File as Document chooses a document
  type of the same kind of record, and Valid For (Days) its validity.
* Each issued print creates a document of that type on the record, numbered
  with the reference of the print, dated on the date of the print, with a copy
  of the PDF. Without a validity, the document does not expire.
* The document is reminded like any other document of Document Expiry.
* Cancelling the print archives its document.
* The issued print links to the document it filed.

Configuration
=============

* Open a template in Print Templates > Templates, go to the Filing tab and
  choose the document type and the validity in days.

Dependencies
============

* Installs by itself with Print Templates (``om_print_template``) and Document
  Expiry (``om_document``).

Support
=======

Odoo Mates, odoomates@gmail.com
