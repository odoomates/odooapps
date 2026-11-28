=========
Documents
=========

Document management for Odoo 20 Community: the files of the company in folders,
with access rights, tags, preview, versions, upload by email, share links,
upload links, document requests and workflow actions, and expiring documents
(passports, permits, licenses, certificates) with reminders and renewals.

Folders and access
==================

* Folders in a tree, shown as a side panel of the documents.
* Each folder says what all the Documents users do in it (no access, view or
  edit), and adds groups and users who read or edit it. Its owner always edits
  it. A subfolder inherits the access of its parent, and adds its own.
* My Drive: a private folder per user, reached by that user only.
* Folders per company, or shared with all the companies.
* Groups: Documents User (the folders shared with them) and Documents
  Administrator (all the folders but the private ones of the other users, the
  tags, the actions and the settings).

Documents
=========

* A file or a link, in a folder, with its tags (tag categories per folder),
  owner, contact and the record it stands for (any model).
* Drag and drop many files on the documents to upload them, or use Upload.
* Preview of images, PDF, videos and text files in the file viewer, from the
  card or in the form.
* Versions: upload a new file in the form, the previous one is kept in the
  versions and can be restored.
* Lock a document to stop the others changing it; star the documents you use.
* Search by name, tag, contact, owner, file type, date, starred, locked,
  requested; chatter and activities on each document.
* Multi-select actions: share, download (zip), move or tag, run an action,
  lock or unlock.

Upload by email
===============

Give a folder an email alias: each file emailed to it becomes a document in the
folder, the sender as its contact, with the tags of the folder for the emailed
documents.

Share links
===========

* Share a folder (with or without its subfolders) or chosen documents with a
  secret link, valid until a date (the default validity is a setting).
* The visitors preview and download the files, one by one or all of them as a
  zip.
* Upload links: the visitors, e.g. customers or vendors, upload files into the
  folder from a public page; the uploads get the tags and the owner of the
  share.
* Send the link by email to the contacts of the share; they also find it in
  their portal, under Documents.
* Each visit, download and upload is logged, with the refusals of expired
  links.

Requests
========

Request a document from a contact: a missing document waits in the folder, the
contact gets an email with a link to upload it, and the user an activity until
it arrives. The requests show as missing or received.

Actions
=======

Workflow actions per folder (and tags or a filter): move the documents, add or
remove tags, set the owner or the contact, schedule an activity, archive them,
and create a record of any model from each document, its file attached and,
optionally, put in a field of the record. The bridges add more: vendor bills,
invoices, signature requests.

Expiring documents
==================

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

Expiring documents: the holder API
==================================

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

Bridges
=======

* Documents - Accounting: bills, invoices and credit notes from documents, and
  the files of the invoices in an Accounting folder.
* Documents - Sign: signature requests from PDF documents, the signed PDF saved
  back as a new version.
* Documents - Project: a folder per project with the files of its tasks,
  shared with the customer of the project.
* Documents - Product: a folder per product with its sheets and manuals.

For developers: a model inheriting ``om.documents.mixin`` gets a Documents smart
button, and the files attached to its records are copied in the folder it gives
in ``_get_documents_folder``, filled with ``_get_documents_values``.

Configuration
=============

* Documents > Configuration > Folders: the folders, their access, tags, actions
  and email alias.
* Documents > Configuration > Settings: the validity of the share links and the
  folders of the apps.
* Documents > Configuration > Document Types: the types of the expiring
  documents. The Expiring Documents folder is reached by the Documents
  administrators: give the people managing those documents access to it, or a
  folder per type.

Upgrading from Document Expiry
==============================

Documents replaces Document Expiry, under the same technical name. On upgrade,
the document types and the documents are moved to Documents with all their
values, files, chatter, activities, followers and reminders already sent; the
note of a document becomes its description, its first file its file and the
other files its extra files. The documents go to the Expiring Documents folder
(or the folder of their record), and the administrators of Document Expiry
become Documents administrators. Customizations on the old models
``document.document`` and ``document.type`` move to ``om.documents.document``
and ``om.documents.type``: custom fields, saved filters, server and scheduled
actions, automations and email templates; code and views written for the old
models must be adapted.
