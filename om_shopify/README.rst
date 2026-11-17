=================
Shopify Connector
=================

Connects Shopify stores to Odoo 20 through the Shopify Admin GraphQL API: products, stock, customers,
orders, fulfillment, refunds and payouts, by webhooks and scheduled imports, every sync being a job that can
be followed and tried again (Connector Base).

Features
========

* **Connection**: client ID and secret of a Dev Dashboard app (token renewed daily), installation by link
  (OAuth, with expiring tokens refreshed by themselves), or the access token of a custom app. Secrets are
  stored encrypted. A setup wizard: Shopify > Configuration > Connect a Store.
* **Webhooks**: checked with the signature of Shopify and the store, queued and answered at once, a webhook
  sent twice run once; the privacy (GDPR) webhooks are handled.
* **Products**: import (bulk operation for the whole catalogue, then changes daily and by webhook), linked by
  SKU or barcode or created with their variants and images; export from Odoo with variants, prices, weight,
  image and publication; a CSV or Excel file to link catalogues whose codes do not match; metafields mapped
  to Odoo fields.
* **Prices**: sent from a pricelist, with compare-at prices, and to Shopify price lists (markets, B2B).
* **Stock**: sent per Shopify location from the warehouse of the location, with limits per variant; or
  imported from Shopify.
* **Customers and B2B**: customers with their addresses; B2B companies, locations, payment terms and tax
  exemption (Shopify Plus).
* **Orders**: imported by webhook, every 15 minutes, or by number; discounts, shipping, taxes of Shopify or of
  Odoo, tips, duties, gift cards, custom items, currency of the customer; confirmed, invoiced and paid by a
  workflow chosen by order rules (payment method, payment and fulfillment status, tag, channel); risky orders
  held; edits applied.
* **After the sale**: fulfillment with tracking number when the delivery is done; cancellations both ways;
  Shopify refunds as paid credit notes and returns; credit notes refunded in Shopify.
* **Payouts** (optional): bank statement lines, or one journal entry per payout through a transit account,
  matched with the payments and the bank transaction.

Setup
=====

1. Create an app in the Shopify Dev Dashboard with the Admin API scopes listed on the store, and install it.
2. Shopify > Configuration > Connect a Store: the address of the store and the credentials of the app.
3. For webhooks, the public https address of Odoo (Odoo Public URL), also set in the app as the compliance
   (GDPR) address; for the installation by link, the App URL and the Redirection URL shown on the store.
