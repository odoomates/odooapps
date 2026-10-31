======================
Sign: Print Templates
======================

Sends the issued prints of Print Templates for electronic signature with Sign. Installs by itself once both
Sign (``om_sign``) and Print Templates (``om_print_template``) are installed.

Features
========

* A print template names who signs its prints, in their order: a contact or user of a field of the record
  (e.g. the customer of a sale order), a given contact, or the person sending. The roles of the same sequence
  sign together.
* The template sets whether the signers confirm their email with a code, the days to sign and the days
  between reminders.
* Placeholders such as ``[signature: Employee]`` put a signature where it belongs in the text of the print;
  the signers without a placeholder sign below the text. The print shows blank blocks until it is signed.
* An issued print is sent for signature from its form (Send for Signature); Issue & Send for Signature in the
  Print wizard does both at once. The print lists its signature requests.
* The signed PDF is the print with the signatures, followed by the signature certificate, which names the
  print. The verification page of the print (its QR code) lists who signed it.

Configuration
=============

* On a print template, the Signers tab lists who signs, with the placeholder of each role, whether an email
  code is needed, the days to sign and the days between reminders.
* Sign > Configuration > Print Templates opens the print templates, for the managers of Print Templates.

Usage
=====

* Issue a print of a template with signers, then Send for Signature: the request opens with its signers,
  to check before sending it.
* Or, from the Print menu of a record, Issue & Send for Signature.

Dependencies
============

* Sign (``om_sign``)
* Print Templates (``om_print_template``)

Support
=======

Odoo Mates, odoomates@gmail.com
