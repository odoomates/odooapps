=============
Consolidation
=============

This module consolidates the companies of a group kept in one Odoo 20 Community Edition database: their
charts of accounts map to one group chart, their balances are translated into the group currency, what they
owe, sell and pay each other is eliminated, and the consolidated trial balance, profit and loss and balance
sheet show a column per company, the eliminations, the adjustments and the group total.

It depends on Inter-Company Invoices and Bills (``om_account_inter_company``): the partners standing for the
companies of the group tell which journal items are inter-company, and its report engine draws the
consolidated reports.

Features
========

* Consolidation groups: the member companies with their ownership (kept for the record: the companies are
  consolidated in full), the parent company, the group currency.
* Group chart: group accounts with a code, a name and a type (asset, liability, equity, income, expense), the
  rate they are translated at and the elimination they take part in. A default group chart, mapped by account
  type, is loaded in one click.
* Account mapping: accounts chosen one by one, ranges of codes (4000 to 4999 takes 400000 to 499999) or
  account types, for every company or for one; Check Mapping lists the accounts with a balance that map to
  nothing, and computing refuses while there are some.
* Consolidation periods (month, quarter, fiscal year of the parent company, or custom dates): Draft, Computed,
  Approved. Approving locks the figures, the rates and the adjustments; Reopen unlocks them.
* Currency translation: assets and liabilities at the closing rate (the rate of the last day of the period),
  income and expense at the average of the rates of the days of the period, equity at the historical rate
  entered per company and account, or carried over from the previous period with the movements since at the
  average rate. The rates can be changed by hand on the period and are then kept. The difference goes to the
  translation reserve, company by company. The income and expense before the period go to the retained
  earnings, carried over from period to period.
* Eliminations:

  * inter-company receivables and payables, and sales and purchases, on the group accounts flagged for it:
    the journal items whose partner is another company of the group;
  * inter-company dividends: the movements of the period of the group accounts flagged for it;
  * the books of each pair of companies side by side, and the differences (what A says B owes against what B
    says it owes A) to the elimination differences account;
  * manual adjustments per period, balanced, on group accounts, for one company or the group.

* Consolidated Trial Balance, Profit and Loss and Balance Sheet, in the accounting reports: a column per
  company translated into the group currency (and in its own currency, as an option), Eliminations,
  Adjustments, Group Total, comparison with another period of the group, key figures, PDF and Excel. A group
  account unfolds into the accounts of each company, the eliminations and the adjustments; a figure of a
  company opens its journal items, in the currency of the company.

Configuration
=============

* Accounting > Configuration > Consolidation Groups: create the group, add its companies, load the default
  group chart (or build one), flag the accounts to eliminate, map the accounts the types do not cover (the
  dividend accounts, for example), enter the historical rates of the equity.
* Accounting > Reporting > Consolidation > Consolidation Periods: create the period, compute it, check the
  rates, the inter-company tab and the reports, add adjustments, approve.
* The currency rates are those of the parent company (or of the company managing the group).

Access
======

* Accounting managers of the company managing the group configure, compute and approve; accounting
  auditors read the periods and the reports.
* A user who may not see every company of the group is refused, with the names of the companies missing; a
  user of another company does not see the group.

Notes
=====

* Full consolidation only: minority interests and netting are not part of this module.
* The figures are those of posted journal items.

Credits
=======

Author: Odoo Mates (odoomates@gmail.com)
