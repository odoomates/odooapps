===================
Documents - Expiry
===================

Expiring documents in Documents: the passport of an employee, the trade
license of the company, the insurance certificate of a vendor. Each one has a
type, a number, an issue and an expiry date, its files, reminders before it
expires and a renewal history. It works for any app: a document type can apply
to any kind of record, or to no record at all.

Features
========

* Document types in Documents > Configuration > Document Types: the kind of
  record they belong to (Applies To, empty for any document), with or without a
  number, an issue date and an expiry date, the reminder days (e.g.
  ``30,7,0``), Notify the Holder, the Responsible Users and an optional folder
  for their documents.
* On every document of Documents: a Document Type, a number, the issue and
  expiry dates, the issuing country, and Extra Files next to its file (e.g. the
  front and the back of an identity card).
* Valid, expiring and expired documents at a glance in Documents > Expiry: a
  kanban with a preview, coloured badges and a sidebar by type, a list, and
  Expiring and Expired filters. A document is expiring once the first reminder
  of its type is due.
* Reminders: a daily scheduled action sends each reminder once, and again after
  the expiry date changes. They go as to-dos to the people the record names
  (e.g. the HR responsible of an employee), else to the Responsible Users of the
  type, else to the owner of the document. With Notify the Holder, the holder
  (or the contact of the document) is emailed too.
* Renew: the new document keeps a link to the one it replaces (Renews, Renewed
  By), which is archived.
* The documents follow the access rights of their folders. A new document goes
  to the folder of its type, else to the folder of its record, else to the
  Expiring Documents folder (with several companies, its subfolder of the
  company of the record, so that the document belongs to that company).
* Multi-company: a type without a company is shared by all the companies.

For developers: the holder API
==============================

A model keeping documents inherits ``om.documents.expiry.mixin`` (which
inherits ``om.documents.mixin``, so its files are copied in its folder as
well). It gets:

* ``document_ids``, ``document_count`` and ``document_alert_count`` (expiring
  and expired), for the Documents users;
* ``action_open_documents()``, the typed documents of the record;
* the Documents widget: ``<field name="document_ids"
  widget="om_documents_expiry_board"/>`` shows a card per document and a card
  per type still missing; drop a file on a card to attach it (the first file of
  a document is its file, the next ones its extra files), or on a missing card
  to create the document;
* hooks to override: ``_document_responsible_users()`` (who is reminded),
  ``_document_holder_partner()`` (who is emailed) and
  ``_get_documents_folder()`` (where its documents are kept).

The holder of a document is its linked record (``res_model``, ``res_id``).
Deleting the record deletes its typed documents.

Configuration
=============

* Give the Documents Administrator access to the people configuring the types,
  and give the people managing the documents access to their folders (the
  Expiring Documents folder is reached by the Documents administrators).
* Create the document types, then add the documents from Documents > Expiry,
  from the Documents widget of a record, or by choosing a Document Type on any
  document.

Dependencies
============

* Documents (``om_documents``)

Support
=======

Odoo Mates, odoomates@gmail.com
