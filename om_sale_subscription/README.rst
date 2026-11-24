=============
Subscriptions
=============

Sell subscriptions from sales orders in Odoo 20 Community: recurring plans,
prices per plan, invoices created every period, automatic payments with the
saved payment method of the customer, upsell and renewal quotations, pause and
close, a customer portal and MRR, ARR, churn and retention reports.

Recurring plans
===============

* Billing period: every N days, weeks, months or years, invoiced at the start
  of each period (in advance) or at its end.
* Recurring invoices: post and send them automatically, or leave them in draft
  to check them first; posting a draft then sends it, uses the online payments
  of the subscription and charges the saved payment method.
* Term: run until closed, or for a fixed duration; at the end of the term the
  subscription renews automatically, gets a renewal quotation (sent a number of
  days before the end) or is closed.
* Unpaid invoices: number of new payment attempts and days between them, and
  close the subscription when an invoice is still unpaid a number of days after
  its due date.
* Customer portal: let customers close, pause and resume their subscription.

Products
========

* A **Subscription** option on products: these products become recurring lines
  on subscriptions.
* Recurring prices per plan, optionally per variant and per pricelist. Without
  a price for the plan, the sales price is used.

Subscriptions
=============

* A subscription is a sales order with a recurring plan: pick the plan on a
  quotation (or on a quotation template) and confirm it.
* Status: quotation, in progress, paused, renewed, closed.
* Start date, next invoice date, end date, recurring total, monthly and annual
  recurring revenue (MRR, ARR), health, tags, close reason.
* One-off lines (setup fees, onboarding) are invoiced with the first period.
* **Upsell**: a quotation with the current lines; the quantities added are
  invoiced for the rest of the current period (prorated to the next invoice
  date) and added to the subscription for the next periods.
* **Renew**: a renewal quotation starting at the end of the term; once
  confirmed, it takes over from the original subscription.
* **Pause**, **Resume**, **Close** with a reason and a note, **Reopen**.
* Saved payment method of the customer, failed payments and next retry.

Invoicing and payments
======================

* A daily scheduled action creates the invoice of each due subscription, one
  per period, with the dates of the period on the lines; it posts and sends it,
  or leaves it in draft when the plan says so.
* When the subscription has a saved payment method, the invoice is charged
  automatically when it is posted. A failed payment sends an email to the customer, is tried
  again later, and the subscription is closed after the grace period of its
  plan.
* A subscription paid online when the quotation is accepted saves the payment
  method used, and the first invoice is reconciled with that payment.
* **Generate Invoice** on the subscription creates the invoice of the next
  period at once.

Customer portal
===============

* **Subscriptions** in the customer portal: the list, and a page per
  subscription with its plan, next invoice, lines and invoices.
* Pay the open invoices, choose the saved payment method charged for the next
  invoices, or add a new one.
* Pause, resume or close the subscription when the plan allows it.

Emails
======

Templates for the invoice of a period, a payment failure, the closing of a
subscription and the renewal quotation.

Reports
=======

* **MRR Analysis**: every change of recurring revenue (new, expansion,
  contraction, churn, transfer to a renewal) with its date; the cumulated graph
  is the MRR over time, the ARR change is shown next to it.
* **MRR Movements**: new, expansion, contraction and churn month by month.
* **Subscription Analysis**: subscriptions by plan, status, customer, country,
  salesperson and close reason, with their MRR and ARR.
* **Retention**: subscriptions grouped by the month they started, with the
  share still running and the share closed.

Configuration
=============

Subscriptions > Configuration: recurring plans, close reasons and quotation
templates with a plan.

Not included
============

Recurring deliveries of storable products, subscriptions sold on the website
shop, commissions and field service contracts are not part of this module.

Credits
=======

* Odoo Mates
