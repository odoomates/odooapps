======================================
Dynamic Accounting Reports - Deferrals
======================================

Adds three reports to the Dynamic Accounting Reports, from Assets Management:

* **Deferred Revenue**: the revenue invoiced in advance (asset categories of
  type Sale: Revenue Recognition).
* **Deferred Expense**: the expenses paid in advance (asset categories of type
  Purchase whose asset account is a prepayment or a current asset account; the
  fixed assets stay out).

* **Depreciation Schedule**: the fixed assets (the other purchase categories),
  by category: the gross value at the start of the period, the additions, the
  disposals and the gross value at its end; the accumulated depreciation at the
  start, the depreciation of the period, what the disposals removed and the
  accumulated depreciation at the end; the net book value. A sale or a disposal
  removes what was left. Click a depreciation figure to open its entries.
  Group the assets by category, asset account, asset group or analytic account.

The deferrals are recognition schedules: per deferral, its total, what it recognized
before the period, in each month of the period (quarters or years for a long
period) and what it still recognizes later, by category. Show the posted and the
planned recognitions, or the posted ones only. Click a figure to open its
recognition entries, a deferral to open it.

The module installs by itself with Dynamic Accounting Reports and Assets
Management.

Release Notes
=============

18.0.1.1.0
----------

* Depreciation Schedule grouped by category, asset account, asset group or
  analytic account. Upgrade with ``-u om_dynamic_reports_asset``.

Credits
=======

Odoo Mates, odoomates@gmail.com
