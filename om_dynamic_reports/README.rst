==========================
Dynamic Accounting Reports
==========================

The accounting reports of Odoo 20 Community on screen: filters at the top,
accounts and partners that unfold into their journal items, drill-down to the
entries behind every figure, saved views, and export to PDF, Excel and CSV as
shown.

Reports
=======

* **Executive Summary**: the key figures on one page. Profitability (revenue,
  cost of revenue, gross, operating and net profit, margins), cash (received,
  spent, surplus, closing balance), balance sheet (receivables, payables,
  working capital, assets, liabilities, net assets) and ratios (current and
  quick ratios, days sales and days payable outstanding, return on assets).
  The figures are those of the other reports; compare them with earlier
  periods, click an amount to see its journal items.
* **Balance Sheet**: assets, liabilities and equity at a date, from the
  sections of Accounting Financial Reports (your own sections too), each
  unfolding into its accounts; the result of the years shows in the Profit
  (Loss) to report, so the report balances.
* **Profit and Loss**: income and expense of a period, closed by the net
  profit.
* **Cash Flow Statement** (direct method): the cash at the start, the cash
  received and paid by operating, investing and financing activities, each
  line unfolding into its accounts, the net change and the cash at the end. The
  cash is followed through the outstanding receipts and payments to what it
  paid, as in the PDF report; an account can be moved to another section with
  its Cash Flow Activity. Or by the **indirect method**: the net profit, the
  depreciation added back, then the changes in receivables, payables and the
  other current accounts, the fixed assets and the financing; both methods
  explain the same change of the cash.
* **Analytic columns** on the Balance Sheet, the Profit and Loss and the Trial
  Balance: pick analytic accounts, or whole plans, and each gets a column with
  its share of every entry, as its analytic distribution splits it (60/40...).
  Each period keeps its own Total of every entry, with or without analytic, so
  amounts left without analytic or split over several accounts never make a
  sum of columns look like the total. They combine with the comparison periods.
  The analytic amounts are those of the posted entries.
* **Horizontal groups** on the Balance Sheet, the Profit and Loss and the
  Trial Balance: set them up in Configuration > Accounting > Horizontal Groups
  with one or more fields of the journal items (journal, partner, product,
  salesperson...), and each value found in the entries of the report gets a
  column; with two fields, each combination of values. A domain keeps some
  values only. Each period keeps its own Total, the columns combine with the
  comparison periods, and any figure opens its journal items. A report shows
  either a horizontal group or analytic columns, at most 50 columns.
* The three statements compare with the same period of the previous years or with the previous
  periods, up to twelve columns, with the variation in % against one period;
  debit and credit columns on demand.
* **Trial Balance**: per account, the initial balance, the debit and credit of
  the period and the ending balance, each split in debit and credit columns
  (the balance columns can be shown too). The income and expense of the
  previous fiscal years show as Undistributed Profits/Losses, so the report
  balances. Compare with earlier periods: each period repeats its initial,
  movements and ending block. Group the accounts by category and account type,
  by parent account, or by account code.
* **General Ledger**: every account with its debit, credit and balance; an
  account unfolds into its initial balance and its journal items with date,
  journal, partner, label, matching number, amount in currency and the running
  balance, page by page. Sort the items by date, or by journal and partner;
  group the accounts by parent account or by account code.
* **Partner Ledger**: every customer and vendor on the receivable and payable
  accounts; a partner unfolds into its initial balance and its journal items
  with due date and matching number. Receivable, payable or both; with or
  without the reconciled entries; all partners, or those with a balance, a
  debit balance or a credit balance.
* **Aged Receivable** and **Aged Payable**: what each partner owes or is owed
  at a date, spread over not due, the overdue periods and older; a partner
  unfolds into its open items with invoice date, due date and days overdue.
  Age by due date or by invoice date; choose the days per period and the number
  of periods. An item paid after the date is still open at the date, as in the
  PDF report; amounts owed to vendors show as positive amounts.
* **Day Book**: day by day, the debit and credit of the day, unfolding into
  every journal item with its entry, journal, account and partner.
* **Bank Book** and **Cash Book**: the general ledger of the accounts of the
  bank (cash) journals, their own account and the outstanding receipts and
  payments accounts of their payment methods, as the PDF books take them: the
  initial balance, every receipt and payment, the running balance.
* **Tax Report**: per tax, the base and the tax of the sales, the purchases and
  the withholding taxes, and the net tax due; a tax unfolds into its accounts.
  Only the tax due on the period counts (a cash basis tax on its payment), as in
  the PDF report. Click a base or a tax to see its journal items.
* **Tax Return**: the tax return of your country as its localization lays it
  out (Belgium, France, Germany...), grid by grid, with the totals of the
  grids; click a grid to see the journal items it adds up. The figures are those
  of the PDF Tax Report by Tax Grid.
* **EC Sales List**: per customer of another country of the European Union with
  a VAT number, the goods and the services invoiced in the period, the credit
  notes deducted; click an amount to see the invoice lines. For the companies of
  the Union.
* **Journals Audit**: every journal with its debit and credit; a journal
  unfolds into its entries (by date or by number), an entry into its journal
  items, and the taxes of the journal at the end.
* **Bank Reconciliation**: per bank and cash journal at a date, the bank balance
  of the books against the last bank statement, the transactions not in a
  statement yet, the bank receipts and payments still to match, the payments
  registered that the bank has not shown yet (outstanding receipts and
  payments), and the bank balance once all of it is matched. Each list unfolds
  into its items; as at a past date too.
* **Customer Statement** and **Vendor Statement**: per partner, the activity
  of the period between the opening balance and the amount due, or the items
  still open at the date, with a summary of what is overdue. Download the
  statement of a partner as a PDF headed with its address, or send it by email
  from the line.
* **Analytic Report**: income, expense and balance of the analytic lines of a
  plan, grouped by analytic account, partner, account, product or journal, in
  any order, down to the analytic lines.

With **Assets Management** (om_account_asset) installed, the module
*Dynamic Accounting Reports - Assets and Deferrals* (om_dynamic_reports_asset)
installs by itself and adds the **Depreciation Schedule**, the **Deferred
Revenue** and the **Deferred Expense**.

Custom financial reports
========================

Beside the Balance Sheet and the Profit and Loss, build reports of your own (a
management P&L, operating expenses, a gross margin) and open each one from a
menu of its own:

1. In Configuration > Accounting > Financial Reports, create a report and add
   its sections: accounts, account types, the value of another report, or the
   sum of the sections below. Each section has its sign and its level of
   detail.
2. On the form of the report, click **Add to Menu** and pick the menu name, the
   parent menu and the position among its menus.
3. Open the new menu: the report opens on screen, with the filters, the
   comparison, the unfolding, the saved views and the exports of the other
   reports. On the form of the report, **Dates** says whether it covers a period
   (as a profit and loss) or stands at a date (as a balance sheet), and **Total
   Line** whether it ends with the amount of the report itself. Each report
   keeps its own saved views and folds.

**Remove Menu** takes the menu away again, and deleting the report removes its
menu too. The accounting managers add the menus; the menu shows for the users
who see the statement reports.

On screen
=========

* Periods from the fiscal year of the company: this month, quarter, financial
  year, the previous ones, or a custom range; arrows move to the previous or
  next period.
* Posted entries only, or the draft ones too.
* Filters on journals, accounts, account tags, partners, partner tags and
  analytic accounts, and on the saved filters (favorites) of the Journal Items
  list: the journal items of any of them.
* Comparison with a period of custom dates.
* Amounts with decimals, in units, in thousands (K) or in millions (M).
* Click an account to unfold it, the list icon to open its journal items, an
  item to open its journal entry; the "..." menu of a Trial Balance account
  opens it in the General Ledger.
* Click a figure of the Balance Sheet, the Profit and Loss or the Trial Balance
  to open exactly what makes it: the journal items of its period (a compared
  period too), of the initial or the ending balance, or the analytic lines of an
  analytic column, with the share its distribution gives it.
* Show, hide and reorder the columns; search in the report; unfold or fold
  everything.
* Saved views: keep the filters and columns under a name, open one by default,
  share it with the other users.
* PDF in the layout of the company (A4 landscape), Excel with real numbers,
  dates and foldable groups, and CSV; with the lines unfolded on screen, or all
  of them.

The figures are the ones of the PDF reports of Accounting Financial Reports:
the same initial balances, the same handling of the fiscal year, the same
branches.

Several companies and currencies
================================

The reports cover the companies selected in the company switcher, with the
branches they consolidate. Pick the **Currency** of a report to show it in
another currency than the one of the company (the books of every company are
converted to it the same way).

The rates are those of Accounting > Configuration > Currencies, for the dates of
the report, not of today, so that a report shows the same figures when printed
again later:

* the balances (Balance Sheet, ledgers, Trial Balance, aged balances,
  statements) at the rates of the end date of the report;
* in the Balance Sheet, the Profit and Loss, the Cash Flow and the Executive
  Summary, the income, the expenses and the cash flows month by month at the
  average rate of each month (each rate weighed by the days it applies), as
  IAS 21 asks;
* the difference this makes in the Balance Sheet is the **Currency translation
  adjustment**, a line of the equity, and in the Cash Flow the **Effect of
  exchange rate changes on cash**, so that both still add up.

The exports say which companies, which currency and which rates.

Menus
=====

Accounting > Reporting > Dynamic Reports, and the menus you add to your own
financial reports (see Custom financial reports). The PDF reports keep their menus. To
hide the menus you do not use, install the free **Restrict Menu** app
(``om_restrict_menu``) and hide them per user.

Access
======

* Balance Sheet, Profit and Loss, Cash Flow, Trial Balance and General Ledger: the
  accounting administrators and auditors.
* Partner Ledger, Aged Receivable, Aged Payable and the statements: the billing
  users too.
* Analytic Report: the accounting administrators and auditors, with analytic
  accounting enabled.

Upgrade
=======

Version 20.0.1.2.0 adds reports and options: upgrade it together with Dynamic
Report Engine. From the command line::

    odoo-bin -c <your config> -d <your database> -u om_report_engine,om_dynamic_reports --stop-after-init

Release Notes
=============

1.3.0
-----

* Tax Return: compared with earlier periods or custom dates, the columns of the
  return repeated under each period, with the variation for a return of one
  amount column; a figure of a compared period opens its journal items.
* Upgrade with ``-u om_dynamic_reports``.

20.0.1.2.0
----------

* Tax Return: the tax return of the country as its localization lays it out,
  grid by grid, each grid opening its journal items.
* EC Sales List: the sales to the customers of the other countries of the
  European Union with a VAT number, goods and services apart (companies of the
  Union).
* Saved journal item filters as a filter of the Balance Sheet, the Profit and
  Loss, the Trial Balance, the General Ledger, the Partner Ledger, the Journals
  Audit and the Day Book.
* Amounts in units, thousands or millions; comparison with custom dates.
* With Budget Management, Dynamic Accounting Reports - Budgets adds the budget
  to the Profit and Loss; with Currency Revaluation, Dynamic Accounting Reports
  - Currency Revaluation adds the unrealized currency gains and losses.

Credits
=======

Odoo Mates, odoomates@gmail.com
