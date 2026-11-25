=============================
Shiprocket Shipping Connector
=============================

Ship with many Indian couriers through your own Shiprocket account, from the
standard delivery methods of Odoo 20 Community.

Features
========

* **Rates** on quotations (Add shipping) and at the website checkout, from the
  pincode of the pickup location, the pincode of the customer, the weight, the
  declared value and the payment mode (COD or prepaid).
* **Courier choice**: recommended by Shiprocket, cheapest, fastest or a fixed
  courier ID; optionally only Surface or only Air couriers.
* **Shipment on validation** of the delivery: Shiprocket order (adhoc), AWB
  assigned with the chosen courier, pickup requested, label and manifest PDFs
  attached to the delivery. The AWB is the tracking reference.
* **Cash on delivery**: when the order was paid with the Cash on Delivery
  payment method of Odoo, always, or never. The amount to collect includes the
  shipping charges of the order. The delivery method can offer Cash on
  Delivery on the website.
* **Tracking** link (Shiprocket tracking page) on the delivery and in the
  customer portal; **Status** button posting the latest tracking event.
* **Cancel** the shipment in Shiprocket from the delivery and send it again.
* **Check Connection** logs in, lists the pickup locations and fills in the
  pickup location and its pincode.
* The token of the API user is cached and renewed before it expires (10 days).

Configuration
=============

1. In Shiprocket, create an API user (Settings, API, Configure, Create API
   User). Its email must be different from your login email.
2. In Odoo, Inventory, Configuration, Delivery Methods: create a delivery
   method with the provider **Shiprocket**.
3. In the **Shiprocket Configuration** tab, enter the email and password of the
   API user (visible to administrators and inventory managers only), click
   **Check Connection**, then set the courier choice, cash on delivery rule and
   a package type with the dimensions of your usual box.
4. Make sure the Delivery Orders operation type has *Generate Shipping
   Labels* checked, so that validating a delivery creates the shipment.

Notes:

* Shiprocket has no test environment: the Test/Production button of the
  delivery method does not change the account used; shipments are created on
  your account.
* Weights are sent in kg, dimensions in cm, amounts in INR (converted from your
  currency when it is not INR).
* A delivery is sent as one Shiprocket shipment: the packages are added up in
  one weight, with the dimensions of the largest package type.

Shiprocket API documentation
============================

* API reference: https://apidocs.shiprocket.in/
* API user: https://support.shiprocket.in/support/solutions/articles/43000604103-how-to-create-an-api-user-can-i-have-more-than-one-api-users-
* API help sheet: https://support.shiprocket.in/support/solutions/articles/43000337456-shiprocket-api-document-helpsheet

What was verified
=================

The requests and the reading of the answers follow the request and response
samples of the Shiprocket API reference above (login, serviceability, create
order, assign AWB, generate pickup, label, manifest, tracking, cancel, pickup
locations). They were tested end to end against a local server answering with
those documented samples, not against a live Shiprocket account. Before going
live, check with your own account: a rate on a quotation, one shipment
(AWB, label, manifest, pickup), the tracking status and a cancellation.

Shiprocket is a trademark of its owner. This module is not affiliated with or
endorsed by Shiprocket.

Support
=======

Odoo Mates, odoomates@gmail.com
