======
Rental
======

Rent products from Odoo 20 Community: rental orders with pickup and return
dates, prices per hour, day, week, month or year, availability checks, pickup
and return with late fees and damages, a rental schedule, analysis, a rental
agreement, reminders and the customer portal.

Rental products
===============

* Tick **Can be Rented** on a product (goods or services) and set its rental
  prices: a duration, a unit (hours, days, weeks, months, years) and a price,
  optionally for some variants or for a pricelist only.
* **Extra hour** and **extra day** prices for late returns.
* **Minimum duration** and **preparation time** between two rentals (cleaning,
  checks, transport).
* **Rentable quantity**: how many units can be out at the same time when the
  stock of the product is not tracked.

Rental orders
=============

* A rental order is a sales order with a pickup and a return date (and per line
  if needed).
* The price of a line is the cheapest combination of the rental prices that
  covers the period, e.g. 1 week + 2 days for 9 days. The period and the charged
  duration are written on the line, so they show on the quotation, the order and
  the invoice.
* Status: Quotation, Reserved (confirmed), Picked Up, Returned, plus a **Late**
  flag when the return date has passed and products are still out.
* **Pickup** and **Return** buttons open a wizard with the quantities and notes;
  at return, late fees are computed from the extra hour and day prices and added
  to the order, with damages or extra charges if any.

Availability
============

* The free quantity of a line is the rentable quantity minus the highest
  quantity used at the same time by the other confirmed rentals of the period
  (preparation time included). Late rentals stay busy until they come back.
* A warning shows when the quantity is not free, with the next date the quantity
  is free for the same duration.
* With **Rental - Stock** (installed automatically with Inventory), the free
  quantity comes from the stock of the warehouse.

Schedule and reports
====================

* **Schedule**: calendar of the rental lines, coloured by product.
* **Rental Analysis**: revenue and units rented per day, per product, customer,
  salesperson; **Utilisation**: share of the rentable quantity in use.

Documents and emails
====================

* **Rental Agreement** printout with the pickup and return dates, the products,
  the terms and conditions of the company and signatures.
* Emails: rental confirmation (with the agreement), pickup reminder and return
  reminder sent by a scheduled action, a set number of hours before the date.
* Portal: rental orders show their period in My Orders and on the order page.

Configuration
=============

Rental > Configuration > Settings: late fee and damage products, reminder delay,
rental terms and conditions.

For developers
==============

* Availability: ``product.product._rental_get_available_qty(start, stop,
  exclude_line=None, company=None, warehouse=None)`` and
  ``_rental_get_next_free_date(...)``; override them to plan per resource.
* Rental lines keep ``rental_start_date``, ``rental_return_date`` and
  ``rental_busy_stop`` (return plus preparation time), stored, with the product
  to group by.
* ``sale.order.line._rental_sync_booking()`` is called on confirmation, pickup,
  return, cancellation and date changes.
