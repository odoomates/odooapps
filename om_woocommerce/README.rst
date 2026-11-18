=====================
WooCommerce Connector
=====================

Connects WooCommerce stores to Odoo 19 through the WooCommerce REST API: products both ways, prices, stock,
customers, orders, completion, refunds and cancellations, by webhooks and scheduled imports, every sync being
a job that can be followed and tried again (Connector Base).

Features
========

* **Connection**: the site address and a REST API key of WooCommerce (Read/Write), stored encrypted; sites
  without pretty permalinks are found and reached through ``?rest_route=``; the key can go in the address for
  servers that drop the Authorization header. Or approve Odoo in WordPress, which sends the key itself. A setup
  wizard: WooCommerce > Configuration > Connect a Store (site, settings, first imports).
* **Webhooks**: created by Odoo with a secret of its own, checked with their signature, queued and answered at
  once; the ping of a new webhook is answered; Sync Webhooks turns on again the webhooks WooCommerce disabled.
* **Products**: simple and variable products imported (changes every day and by webhook), linked by SKU or GTIN
  or created with their variations and images; a CSV or Excel file to link catalogues whose codes do not match.
* **Product export**: Odoo products sent to WooCommerce from Actions > Export to WooCommerce, as simple or
  variable products with their variations, prices, weight, stock, category, tags and attributes; the images
  uploaded to WordPress with an Application Password; publish and unpublish from Odoo.
* **Prices**: the price of a price list, as a sale price under a regular price list when that one is higher;
  sent every day or on demand, by batches.
* **Meta data**: WooCommerce meta keys mapped to Odoo fields of products, variations, customers and orders, on
  import, and sent with the product export.
* **Coupons**: imported and kept in sync by webhook, made or changed in Odoo and sent to WooCommerce, deleted
  from Odoo; each order lists the coupons it used.
* **Stock**: sent from the warehouse of the store every 15 minutes, by batches, with limits per variant; or
  imported from WooCommerce.
* **Customers**: registered customers with their addresses; guests found by email.
* **Orders**: imported by webhook, every 15 minutes, or by number, in the statuses chosen on the store; coupons,
  shipping, fees, taxes of WooCommerce or of Odoo, prices with or without taxes, currency of the order;
  confirmed, invoiced and paid by a workflow chosen by order rules (payment method, status, created via,
  shipping method); each shipping method of WooCommerce mapped to an Odoo carrier.
* **After the sale**: delivered orders completed in WooCommerce, with the tracking number in a note to the
  customer or in the Shipment Tracking extension; cancellations both ways; WooCommerce refunds as paid credit
  notes and returns; credit notes refunded in WooCommerce, through the payment gateway if asked.

Setup
=====

1. WooCommerce > Configuration > Connect a Store: the address of the site.
2. Approve Odoo in WordPress (Odoo must be reachable at an https address), or paste a key made in WordPress,
   WooCommerce > Settings > Advanced > REST API, with the Read/Write permission.
3. For webhooks, the public https address of Odoo (Odoo Public URL).
4. For the images of exported products, a WordPress user and one of its Application Passwords (Connection tab).
