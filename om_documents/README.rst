=========
Documents
=========

Document management for Odoo 20 Community: the files of the company in folders,
with access rights, tags, preview, versions, upload by email, share links,
upload links, document requests and workflow actions.

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

Bridges
=======

* Documents - Accounting: bills, invoices and credit notes from documents, and
  the files of the invoices in an Accounting folder.
* Documents - Sign: signature requests from PDF documents, the signed PDF saved
  back as a new version.
* Documents - Project: a folder per project with the files of its tasks,
  shared with the customer of the project.
* Documents - Product: a folder per product with its sheets and manuals.
* Documents - Expiry: expiry dates and reminders on documents with Document
  Expiry.

For developers: a model inheriting ``om.documents.mixin`` gets a Documents smart
button, and the files attached to its records are copied in the folder it gives
in ``_get_documents_folder``, filled with ``_get_documents_values``.

Configuration
=============

* Documents > Configuration > Folders: the folders, their access, tags, actions
  and email alias.
* Documents > Configuration > Settings: the validity of the share links and the
  folders of the apps.
