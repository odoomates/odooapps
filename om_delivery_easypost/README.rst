===========================
EasyPost Shipping Connector
===========================

Ship with USPS, UPS, FedEx, DHL and the many other carriers of your own
EasyPost account, from the standard delivery methods of Odoo 20 Community.

Features
========

* **Rates** on quotations (Add shipping) and at the website checkout: the
  cheapest or the fastest rate among the carrier accounts, carriers and
  services you allow.
* **Labels** bought when the delivery is validated, attached to the delivery in
  PDF, ZPL or PNG, in the size of your choice (e.g. 4x6).
* **Multi-package**: a delivery packed in several packages is shipped as an
  EasyPost order, with one label and one tracking number per package.
* **Customs** for international shipments: one customs item per product with
  quantity, value, weight, HS code and country of origin from the product;
  contents type, non-delivery option, EEL/PFC and signer on the delivery method.
* **Insurance**: the Insurance Percentage of the delivery method insures each
  shipment for that share of its value.
* **Package types**: dimensions and base weight of the package type; its
  carrier code is sent as EasyPost predefined package (e.g. FlatRateEnvelope).
* **Tracking** page of EasyPost on the delivery and in the customer portal;
  **Status** button posting the latest tracking event.
* **Cancel** asks EasyPost for the refund of the label(s).
* **Test and production** keys: the key of the environment set on the delivery
  method is used.

Configuration
=============

1. In Odoo, Inventory, Configuration, Delivery Methods: create a delivery
   method with the provider **EasyPost**.
2. In the **EasyPost Configuration** tab, enter your test and production API
   keys from the EasyPost dashboard (visible to administrators and inventory
   managers only) and click **Check Connection**. In production it lists your
   carrier accounts.
3. Optionally limit the carrier accounts (ca\_... IDs), carriers and services,
   choose the label format and size, the package type and the customs options.
4. Make sure the Delivery Orders operation type has *Generate Shipping
   Labels* checked, so that validating a delivery buys the label.

Notes:

* Weights are sent in ounces and dimensions in inches, converted from the
  units of Odoo. Rates are converted to the currency of the company.
* The EasyPost Orders API (several packages) supports a subset of the carriers
  (see the EasyPost documentation).
* Addresses need street, city, zip and country; US addresses also a state.

EasyPost API documentation
==========================

* Shipments, buy, labels: https://docs.easypost.com/docs/shipments
* Shipment options: https://docs.easypost.com/docs/shipments/options
* Rates and messages: https://docs.easypost.com/docs/shipments/rates
* Orders (multi-package): https://docs.easypost.com/docs/orders
* Customs: https://docs.easypost.com/docs/customs-infos and https://docs.easypost.com/docs/customs-items
* Insurance: https://docs.easypost.com/docs/shipments/shipping-insurance
* Refunds: https://docs.easypost.com/docs/shipments/shipping-refund
* Trackers: https://docs.easypost.com/docs/trackers
* Carrier accounts: https://docs.easypost.com/docs/carrier-accounts
* Errors: https://docs.easypost.com/docs/errors

What was verified
=================

The requests and the reading of the answers follow the request and response
samples of the EasyPost documentation above (shipments, buy, label
conversion, orders, insurance, refunds, trackers, carrier accounts, errors).
They were tested end to end against a local server answering with those
documented samples (domestic, international with customs, ZPL labels, two
packages, refunds), not against a live EasyPost account. Before going live,
check with your own test key: a rate on a quotation, a domestic and an
international label, a delivery with two packages, the tracking status and a
refund.

EasyPost, USPS, UPS, FedEx and DHL are trademarks of their owners. This module
is not affiliated with or endorsed by them.

Support
=======

Odoo Mates, odoomates@gmail.com
