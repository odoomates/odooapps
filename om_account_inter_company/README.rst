================================
Inter-Company Invoices and Bills
================================

This module connects the companies of a group kept in one Odoo 20 Community Edition database: the customer
invoice one company issues to another becomes the vendor bill of the other, and the report of inter-company
balances shows what each company owes the others, as both sides book it.

It depends on Invoicing (``account``) and on the Odoo Mates report engine (``om_report_engine``).

Features
========

* Rules per pair of companies, one way or both ways:

  * customer invoices and credit notes become vendor bills and refunds of the other company;
  * vendor bills and refunds can become customer invoices and credit notes (when the buying company enters
    the bill first);
  * created in draft, or posted at once;
  * created as an inter-company user of the rule (OdooBot by default): the person posting the invoice needs
    no access to the other company;
  * the PDF of the invoice attached to the bill as its original document;
  * journals of each company, or their first sales and purchase journals.

* Mapping, per rule:

  * accounts: from the products and the journal of the receiving company, or the account with the same code;
    a mapping table first;
  * taxes: the tax of the receiving company with the same rate (a sales tax becomes the purchase tax), or the
    taxes of the product, then the fiscal position of the partner; a mapping table first;
  * products: shared products are kept, products of one company are mapped, else the line keeps its label;
  * analytic distribution copied when its analytic accounts are shared, or left to the receiving company;
  * currency: the bill in the currency of the invoice, or in the currency of the receiving company at the
    rate of the invoice date.

* Both documents linked: a smart button on each, messages in both chatters, the invoice number as bill
  reference and payment reference, the credit note linked with the bill it refunds.
* When the issued document is reset to draft or cancelled, its bill follows (unless paid) or gets a warning,
  as the rule says; posting the invoice again updates a bill still in draft. A document that could not be
  created leaves a warning on the invoice with a Try Again button.
* Accounts flagged Inter-Company, and partners linked with the company of the group they are (set by itself
  on the partner of each company).
* Inter-Company Balances report: per company and other company, what is owed as the company books it, as the
  other company books it, and the difference; key figures, pairs with a difference, grouping by books and
  account, journal items behind each line, presentation currency, PDF and Excel.

Configuration
=============

* Set the partner of each company as the customer or vendor between them.
* Accounting > Configuration > Inter-Company Rules: one rule per pair of companies.
* The user of a rule needs access to the companies it creates documents in, with the rights to create and
  post invoices there.

Notes
=====

* Netting of mutual balances is not part of this module.
* A document created from another is never copied again (no loops between two companies).
* Only posted documents are copied.

Credits
=======

Author: Odoo Mates (odoomates@gmail.com)
