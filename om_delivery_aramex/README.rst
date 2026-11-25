=========================
Aramex Shipping Connector
=========================

Ship with your own Aramex account across the Gulf, the Middle East and the
world, from the standard delivery methods of Odoo 20 Community.

Features
========

* **Rates** (CalculateRate) on quotations (Add shipping) and at the website
  checkout, in the currency of the company.
* **Product group**: domestic when the shipment stays in the country, express
  otherwise, or always one of them; express product type (PPX, PDX, DPX, EPX...)
  and domestic product code (e.g. ONP).
* **Shipment on validation** of the delivery (CreateShipments): the AWB is the
  tracking reference and the label PDF is attached to the delivery (reprinted
  with PrintLabel when the answer has no label).
* **Cash on delivery** (service CODS): when the order was paid with the Cash on
  Delivery payment method of Odoo, always, or never; the amount to collect is
  the total of the order. The delivery method can offer Cash on Delivery on the
  website.
* **Customs value** and items (HS code, country of origin) for express
  shipments.
* **Prepaid or collect** freight, with payment options for collect.
* Number of pieces and weight from the packages, dimensions from the package
  type.
* **Tracking** link (Aramex tracking page) on the delivery and in the customer
  portal; **Status** button posting the latest tracking event
  (TrackShipments).
* **Check Connection** calculates a test rate with your credentials.

Configuration
=============

1. In Odoo, Inventory, Configuration, Delivery Methods: create a delivery
   method with the provider **Aramex**.
2. In the **Aramex Configuration** tab, enter the username, password, account
   number, PIN, entity and country code of your Aramex account (visible to
   administrators and inventory managers only) and click **Check Connection**.
3. Choose the product group and types, payment type, cash on delivery rule,
   label report (9201 is the standard label) and a package type.
4. Make sure the Delivery Orders operation type has *Generate Shipping
   Labels* checked, so that validating a delivery creates the shipment.

Notes:

* The test environment of the delivery method uses the Aramex test services
  (ws.dev.aramex.net) with test credentials from Aramex; production uses
  ws.aramex.net with your live account.
* The Aramex shipping services have no cancellation of shipments: Cancel on
  the delivery clears the AWB in Odoo and leaves a note to ask Aramex to cancel
  it.
* Weights are sent in kg and dimensions in cm.

Aramex API documentation
========================

* Developer center: https://www.aramex.com/us/en/developers-solution-center
* Shipping services (CreateShipments, PrintLabel, CreatePickup, CancelPickup):
  https://ws.aramex.net/ShippingAPI.V2/Shipping/Service_1_0.svc?singleWsdl
* Rate calculator (CalculateRate):
  https://ws.aramex.net/ShippingAPI.V2/RateCalculator/Service_1_0.svc?singleWsdl
* Tracking (TrackShipments):
  https://ws.aramex.net/ShippingAPI.V2/Tracking/Service_1_0.svc?singleWsdl

What was verified
=================

The request and response structures follow the service definitions above;
the JSON endpoints (``.../Service_1_0.svc/json/<operation>``) were checked to
answer on the production host and to reject wrong credentials with the Aramex
notification ERR75. The Aramex test environment (ws.dev.aramex.net) could not
be reached and the test credentials found in public samples were refused, so
the full flow (rate, shipment, label, tracking) was tested against a local
server answering in the documented format, not against a live Aramex account.
Before going live, check with your own account: a rate on a quotation, one
domestic and one express shipment with the label, a COD shipment and the
tracking status. Product type codes depend on your Aramex contract.

Aramex is a trademark of its owner. This module is not affiliated with or
endorsed by Aramex.

Support
=======

Odoo Mates, odoomates@gmail.com
