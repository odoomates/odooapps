===============
Document Expiry
===============

Keep the documents of any record with their number, their dates and their
files, e.g. the passport of an employee, the trade license of a company or the
insurance certificate of a vendor, and be reminded before they expire. It
works for any app, not only HR: a document type can apply to any kind of
record.

Features
========

* Document types per kind of record, with or without a number, an issue date
  and an expiry date, in Expiring Documents > Configuration > Document Types.
* Reminders before a document expires, on the days you choose per type, e.g.
  30, 7 and 0 days before: each one is sent once, and again after the expiry
  date changes. They go as to-dos to the people the record names, e.g. the HR
  responsible of an employee, else to the responsible users of the type. A
  daily scheduled action sends them.
* Optionally, an email to the holder of the document as well.
* Valid, expiring and expired documents at a glance: a kanban with a preview of
  the files, coloured badges, and a sidebar by type. A document is expiring
  once the first reminder of its type is due.
* Renew a document: the new one keeps a link to the one it replaces, which is
  archived.
* The Documents widget on the records keeping them: a card per document and a
  card per type still missing; drop a file on a card to attach it, or on a
  missing card to create the document.
* Multi-company: a document belongs to the company of its record; a type
  without a company is shared by all the companies.
* Another module makes any model keep documents by inheriting
  ``document.mixin``, as HR Documents does for the employees. The model
  names who is reminded in ``_document_responsible_users`` and who holds the
  documents in ``_document_holder_partner``.

Configuration
=============

* Give the Administrator access of Document Expiry to the people who manage
  all the documents.
* Create the document types in Expiring Documents > Configuration > Document
  Types: the kind of record they belong to (Applies To), the fields they have,
  the reminder days (e.g. ``30,7,0``), Notify the Holder, and the Responsible
  Users reminded when the record names no one.

Usage
=====

* Expiring Documents > Documents > Expiring Documents and Expired Documents
  show what needs renewing; All Documents lists every document.
* Open a document to add its files, and use Renew when the new one arrives.

Dependencies
============

* Discuss (``mail``)

Support
=======

Odoo Mates, odoomates@gmail.com
