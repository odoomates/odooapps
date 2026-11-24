==============
Rental - Stock
==============

Links **Rental** and **Inventory**. Installed automatically when both are
installed.

* A **rental location** per warehouse, outside the stock of the warehouse.
* **Pickup** moves the products from the warehouse stock to the rental
  location, **return** moves them back, with stock moves linked to the order
  line (smart button on the order).
* **Lots and serial numbers**: reserve serials on the order line, choose them at
  pickup (serials reserved by other rentals of the period are not proposed);
  the serials picked up are expected back at return.
* **Availability** counts the units in the warehouse and out on rental, minus
  the other confirmed rentals of the period, preparation time included.
* Rental lines do not create deliveries; services are rented without stock
  moves.
