=================================
Inter-Company Sales and Purchases
=================================

This module creates the purchase order of one company of the group from the sales order another company
confirms to it, and the reverse, in one Odoo 20 Community Edition database. The delivery of the selling company
can validate the receipt of the buying company, and the invoice of the order becomes the bill of its purchase
order with the rules of Inter-Company Invoices and Bills.

It depends on ``om_account_inter_company``, ``sale_stock`` and ``purchase_stock``.

Features
========

* On the inter-company rule of a pair of companies:

  * sales orders to purchase orders: confirming a sales order to the other company creates its purchase order;
  * purchase orders to sales orders: confirming a purchase order to the other company creates its sales order;
  * created as a quotation / request for quotation, or confirmed at once with its receipt or delivery;
  * prices of the confirmed order kept (converted to the currency of the order created when needed), or from
    the pricelists of the receiving company;
  * salesperson and buyer of the orders created;
  * warehouse and receipt type of each company.

* Both orders linked with a smart button; the order reference of the other company as vendor or customer
  reference.
* Changes followed from the order that was confirmed: a quantity changed, a line added, the order cancelled
  change the order of the other company while it is not received, delivered or billed; once it is, both orders
  get a warning instead. A change made on the order created warns the order it came from.
* Validating the delivery of the selling company validates the receipt of the buying company with the same
  quantities, lots and serial numbers (option of the rule); what is not delivered stays in a backorder.
* The invoice of a sales order becomes the bill of its purchase order (and the reverse), linked with the
  purchase order lines: the purchase order shows it as billed and nothing is entered twice.

Configuration
=============

Accounting, Sales or Purchase > Configuration > Inter-Company Rules, tab Sales and Purchases.

Notes
=====

* Products of one company only are mapped in the Product Mapping of the rule; a line without a product
  available in the other company is left out with a warning.
* The receipt follows the deliveries of the selling company; returns are not copied.

Credits
=======

Author: Odoo Mates (odoomates@gmail.com)
