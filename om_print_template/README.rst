===============
Print Templates
===============

Print certificates, letters and confirmations from any record: write the
template in the editor with the fields of the record, then print it from the
Print menu of the record. It works for any app, e.g. salary certificates of
employees or balance confirmations of customers.

Features
========

* A template per kind of record, e.g. Employee or Contact, written in the HTML
  editor: type ``{{`` to insert a field of the record. The subject, the
  addressee and the language can use fields too.
* Each template appears in the Print menu of its records, next to the reports
  of Odoo, without any development. Untick In the Print Menu to hide it.
* Print one record or several at once, with a preview of the text.
* Every print gets a reference from the sequence of its template, e.g.
  ``CERT/2026/0001``, and is kept as an issued print with its PDF.
* The text is frozen when the print is issued: printing it again gives the same
  PDF, whatever changed on the record since.
* Edit the text before issuing, e.g. to add a line for an embassy.
* Optionally, a verification QR code on the print. It opens a public page
  stating whether the print is genuine and still valid, without showing its
  text. Cancelling a print shows it as cancelled there.
* The signatory, their title and a signature or stamp image on each template,
  on the company letterhead of the document layout.
* Users see the prints they made; the print administrators see and cancel all
  of them.
* With Document Expiry installed, a template can file each print as a
  document of the record, expiring after a number of days (Print Templates:
  Documents, installed by itself).

Configuration
=============

* Give the Administrator access of Print Templates to the people who write the
  templates and cancel prints.
* Create the templates in Print Templates > Templates: the kind of record
  (Applies To), the reference prefix, the text, the signature, and whether it
  carries the verification QR code.

Usage
=====

* Open a record, use Print, and choose the template: Issue & Download prints it
  at once, Edit Before Issuing opens a draft to adjust first.
* Print Templates > Issued Prints lists every print, to download it again or
  cancel it.

Dependencies
============

* Discuss (``mail``)
* Web (``web``)

Support
=======

Odoo Mates, odoomates@gmail.com
