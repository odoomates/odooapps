=====================
Website Subscriptions
=====================

Sell the subscription products of the Subscriptions app (om_sale_subscription)
on the eCommerce shop, in Odoo 20 Community.

Features
========

* **Published plans**: a "Published on Website" toggle on the recurring plans.
  On the shop, a subscription product offers the published plans that have a
  recurring price for it (per variant and pricelist, as in the backend).
  Unpublished plans never appear on the website and a cart cannot use them.
* **Product page**: with several plans, the customer picks one and sees its
  price per period ("/ month", "/ year"); the price follows the variant and the
  plan. With one plan, it is applied without asking.
* **Cart**: adding a subscription product makes the cart a subscription of the
  chosen plan. A cart holds one plan: a subscription product with another plan
  is refused with a message, one-time products can be added beside it. The
  recurring lines show their period and the summary shows "Then every month"
  with the amount of each period. Removing the last subscription product turns
  the cart back into a normal order.
* **Checkout**: only payment methods that can be saved are offered for a
  subscription; the saved payment method pays the next invoices. Guest checkout
  works: the payment method is saved for the new customer. Express checkout is
  not offered for subscriptions.
* **Start**: paying confirms the order and starts the subscription. It shows in
  Subscriptions and in the customer portal (My Subscriptions).
* **First invoice**: by default, it is created, paid with the online payment
  and emailed to the customer right after the payment, also when "Automatic
  Invoicing" is off in the Sales settings. Turn off "Invoice Subscriptions at
  Payment" to let the daily subscription job create it and match it with the
  payment already made. Only plans that invoice in advance have a first invoice
  at the start; the others are invoiced at the end of each period.
* **Shop**: a "Subscription" badge and the lowest recurring price ("From
  10.00 / month") on the product tiles.

Configuration
=============

* Subscriptions > Configuration > Recurring Plans: turn on "Published on
  Website" on the plans you sell online.
* Products: tick "Subscription", add the recurring prices and publish the
  product on the website.
* Website > Configuration > Settings, eCommerce:

  * "Subscriptions without saved payment method": hide the payment providers
    that cannot save the payment method (default), or allow them; the next
    invoices are then sent by email to be paid by the customer.
  * "Invoice Subscriptions at Payment" (on by default): create, pay and email
    the first invoice right after the payment. Off: the daily subscription job
    creates it.
  * "Show Recurring Prices": show the recurring price instead of the sales price
    on the shop, for subscription-only shops.

Depends
=======
[om_sale_subscription], [website_sale] addons

Installation
============
- www.odoo.com/documentation/20.0/setup/install.html
- Install our custom addon

Credits
=======

Odoo Mates, odoomates@gmail.com
