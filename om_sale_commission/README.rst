=================
Sales Commissions
=================

Pay commissions to your salespersons, sales teams and resellers in Odoo 20
Community: commission plans with rules or targets and achievement tiers,
commission lines computed from invoices or sales orders, statements approved by
the sales manager and paid with a vendor bill, clawback of commissions already
paid, an achievement dashboard and a portal page for resellers.

Commission plans
================

* For **salespersons**, **sales teams** or **resellers**, per company, with a
  validity and a period: monthly, quarterly or yearly.
* Based on **invoices** (counted when posted or when paid; credit notes reduce
  the commission) or on **confirmed sales orders** (a cancelled order is taken
  back).
* **Commission rules**: a percentage of the revenue, a percentage of the margin,
  or a fixed amount per unit, for one product, a product category or all
  products. A rule on a product comes before a rule on its category, which comes
  before a rule on all products. The margin uses the cost of the sales order
  line when Sales Margin is installed, else the cost of the product.
* **Target and achievement tiers**: a target per period (one for all or one per
  salesperson, team or reseller) on the revenue or the margin, and tiers that
  give the commission rate from the share of the target reached, for example
  below 80%: 0%, from 80%: 3%, from 100%: 5%.
* **Cap** of the commission of one person per period.
* **Sales teams**: the commission goes to the salesperson of the document or is
  split equally between the team members, and the team leader can earn an
  override percentage of every commission of the team.

Commission lines and achievements
=================================

* One line per invoice line or order line and beneficiary, with the plan, the
  rule, the revenue, the margin, the rate, the commission and a link to the
  invoice or the sales order.
* Computed every day by a scheduled action for the current and the previous
  period, and on demand with **Recompute**.
* Lines already approved or paid are never computed again. When their invoice is
  cancelled or reset to draft, their order is cancelled or (when counted when
  paid) the invoice is no longer paid, a **clawback** line takes the commission
  back in the current period. A credit note of an invoice already approved or
  paid takes back the commission at its original rate.
* **Achievements**: revenue, margin, target, share of the target reached, tier
  rate and commission per salesperson, team or reseller and period, in kanban
  with progress bars, list, pivot and graph.

Statements and payment
======================

* **Create Statements**: one draft statement per salesperson or reseller with
  every commission not settled yet up to a date, including late commissions and
  clawbacks.
* Draft, **Approved** (by a sales manager), **Paid**, Cancelled.
* **Vendor bill**: invoicing users create the vendor bill of an approved
  statement for the partner of the salesperson or the reseller, with the
  commission product, journal and expense account of the settings; a negative
  statement creates a vendor credit note. The statement is paid when the bill
  is paid.
* **Other** payout: mark the statement as paid by hand, or pay it with another
  tool (such as payslips) using ``_get_payable_amounts()`` and
  ``_set_paid_externally()`` on ``om.commission.statement``.
* PDF commission statement.

Resellers
=========

* A **Referrer** on sales orders and invoices, copied from the order to its
  invoices and credit notes, and proposed from the **Referred By** partner of the
  customer.
* **Reseller grades** (such as Gold and Silver) on contacts: a reseller plan
  applies to its resellers and to every reseller of its grades.
* Reseller statements and vendor bills work like the ones of salespersons.
* **Portal**: resellers with portal access see their approved and paid
  statements under My Account, Commissions, and download them as PDF.

Access rights
=============

* Salespersons see their own commission lines, achievements and statements.
* Sales managers see everything, manage the plans, create and approve the
  statements.
* Invoicing users see the statements and create the vendor bills.

Configuration
=============

* Sales > Configuration > Settings > Commissions: commission product, journal
  and expense account of the vendor bills.
* Commissions > Configuration: plans, reseller grades, resellers.

Credits
=======

* Odoo Mates
