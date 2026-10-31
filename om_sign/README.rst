====
Sign
====

Electronic signatures for Odoo Community: turn any PDF into a template, place the fields each signer fills
on its pages, and send it. The signers sign from a link sent by email, on a phone or a computer, without an
account and in the order set; everyone gets the signed PDF, which ends with a signature certificate.

Features
========

Templates from PDF files
------------------------

* Upload a PDF (Sign > Templates > Upload a PDF): it becomes a template, sent as many times as needed.
* The templates show as cards: the first page of the PDF, the number of pages, the roles in their colours,
  how many requests were sent, signed and made from the shared link, and the buttons Edit Fields, Send and
  Send in Bulk. The list and the form stay one click away.
* The roles sign in their order; the roles of the same sequence sign together. Each role is chosen when
  sending, a given contact, or the person sending.
* A template proposes the email code, the days to sign, the days between reminders, a message for the
  signers and the copy recipients.

The editor
----------

* Edit Fields opens the pages of the PDF. Pick a role, then drop its fields on the pages: signature,
  initials, name, email, company, date, text and checkbox, in the colour of the role.
* Move and resize the fields with the mouse, make them optional, give them a label such as "Job title";
  the fields keep their place whatever the zoom and the size of the page.
* Share, Send and Send in Bulk are in the editor too.

The signing page
----------------

* The signer opens the link of the email and signs on the pages of the document: each of their fields is
  where it belongs, and Start / Next guide them from one field to the next, with the progress on top.
* A signature or initials drawn, typed or uploaded once fills the other ones with a click; the name,
  company, email and date are filled in for them. Finish signs once every required field is filled.
* What the signers before them filled in is shown on the pages, read-only. Once signed, waiting for the
  others or completed, the page shows the document with the values filled so far.
* A signer may decline, with a reason: the request is closed and the person who sent it is told.
* The page shows the company, its logo and name, without the header of the website; it works on phones.
* Optionally, a code sent by email that the signer enters before signing.

Following the requests
----------------------

* Sign > Requests: To Sign (the documents you sign now), Waiting for Others, Completed, and All, as cards
  grouped by status: draft, waiting for signatures, signed, declined, cancelled and expired.
* Each card shows the document, its template, a progress bar of the signatures, the signers as avatars
  marked with their status, the deadline (red once past), whether it was sent in bulk or made from the
  shared link, and the person who sent it.
* The request shows the timeline of its signers, in their order: asked, opened, email verified, signed or
  declined, with the dates and the reminders sent. The smart buttons open the signed PDF, the record signed
  for and the template; the tabs list the signers, the fields filled in and the evidence.
* Sign opens on All for the administrators of Sign, on To Sign for the others.
* Reminders every few days, and a deadline after which the request expires.

Copy recipients
---------------

* Contacts who do not sign: they are told when the document is sent (optionally) and get the signed PDF,
  with a link to a read-only view of the document. Proposed by the template, set when sending or on a draft
  request.

Send in Bulk
------------

* One request per contact for one role, e.g. the same agreement to 50 customers, the other roles signed by
  the same people in every request. More than 20 requests are sent in the background.

The shared link
---------------

* Share a template by a public link, from its Share tab or the editor, when exactly one role is chosen when
  sending: the visitor signs as it.
* The visitor gives their name and email and confirms the email with a code sent to it; the request is
  then made and they sign straight away. The other roles, a given contact or the person sending, sign next.
* The person who turns sharing on is the requester of the requests made from the link: they are sent as
  them, and they follow them. A new link can be made at any time; the old one stops working.
* The requests a visitor may make are limited per hour, by email and by IP address (see Configuration).

PDF files without a template
----------------------------

* A PDF uploaded on a request, without a template, is signed as it is: a signature page with the signature
  of each signer is added at its end.

Print templates
---------------

* With Print Templates (``om_print_template``), Sign: Print Templates (``om_sign_print_template``) installs
  by itself: the issued prints are sent for signature, the signers named by their template, with
  placeholders such as ``[signature: Employee]`` where each signs in the text.

Proof
-----

* The signed PDF ends with a certificate: who signed, when, from which IP address and browser, and the
  SHA-256 fingerprint of the document sent. A public page confirms a signed document from its reference.
* Everything that happens is kept as evidence that nobody can change.
* The signers find the documents sent to them in the Signatures page of the portal; users of the backend
  sign from Sign > Requests > To Sign.

Configuration
=============

* Give the User access of Sign to the people who send documents for signature, and the Administrator
  access to the people who see all the requests and all the templates.
* The requests a visitor of a shared link may make per hour are set by two system parameters (Settings >
  Technical > System Parameters):

  * ``om_sign.share_limit_email``: per email address, 5 by default;
  * ``om_sign.share_limit_ip``: per IP address, 20 by default.

Usage
=====

* Sign > Templates > Upload a PDF makes a template and opens its editor: place the fields of each role,
  Save, then Send: choose who signs as each role, the copy recipients, the deadline, and send.
* Send in Bulk, from the template card, its form or its editor: choose the role and the contacts.
* Share, from the editor or the Share tab of the template: turn the link on and copy it, e.g. into a web
  page or an email.
* The first page of a template is drawn by the browser the first time its card is shown, then kept with the
  template; uploading another PDF draws it again.

Developers
==========

The ``sign.mixin`` abstract model gives any model a Signatures smart button (``sign_request_count``,
``action_open_sign_requests``), a button sending a PDF about the record for signature
(``action_request_signature``) with the signers it suggests (``_sign_default_signers``), and hooks called
when a document about the record is signed, declined or cancelled (``_on_sign_completed``,
``_on_sign_declined``, ``_on_sign_cancelled``). The Odoo Mates HR apps use it for the employees, the
offers and the onboarding.

Editions
========

Works with Odoo 20 Community and Odoo 20 Enterprise. On Enterprise, it cannot be installed together with
the Enterprise Sign app (``sign``): both define the same records. Use one or the other.

Dependencies
============

* Discuss (``mail``)
* Portal (``portal``)

Support
=======

Odoo Mates, odoomates@gmail.com
