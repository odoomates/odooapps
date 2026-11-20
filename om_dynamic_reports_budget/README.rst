=====================================
Dynamic Accounting Reports - Budgets
=====================================

Adds the budgets of Budget Management to the Profit and Loss of the Dynamic
Accounting Reports.

* Pick one or more budgets in the **Budgets** filter of the Profit and Loss: a
  **Budget** column shows what they plan for the period, next to the balance,
  and an **Achievement %** column the balance as a percentage of the budget.
* A budget line counts for the days of the period in its own period.
* A budgetary position of several accounts is spread over them in proportion to
  what they booked in the period (evenly when they booked nothing), so that the
  sections add up to the budget of their positions.
* The budget columns show for the period of the report, without analytic
  columns or a horizontal group.

The module installs by itself with Dynamic Accounting Reports and Budget
Management.

Release Notes
=============

18.0.1.1.0
----------

* The budget columns follow the comparison: each period compared gets its
  Balance, Budget and Achievement %, under the label of the period.
* Upgrade with ``-u om_dynamic_reports_budget``.

18.0.1.0.0
----------

* First version.

Credits
=======

Odoo Mates, odoomates@gmail.com
