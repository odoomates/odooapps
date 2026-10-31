================
Loans and Leases
================

This module manages the loans a company receives from banks and other lenders,
and the leases it holds, in Odoo 20 Community Edition: the contract, its
amortization schedule, the drawdowns, the instalments, the early repayments,
the floating rates, the lease liability and the bills of the lessor, the
withholding tax on the interest, the schedules imported from the lender, the
current and non-current reclassification and a loan report.

Features
========

* Record a loan: the lender and its reference, the principal, the currency,
  the start date, the first payment date, the number of payments and their
  frequency (monthly, quarterly, semi-annual or annual), a fixed or floating
  annual rate, the accounts and the journals. Loans are numbered LOAN/year/0001
  and move from Draft to Running, then Closed (or Cancelled).
* Three schedule methods: equal instalments (annuity), fixed principal, or
  the schedule of the lender imported from a CSV or XLSX file.
  100,000 at 6% over 12 monthly payments gives 12 instalments of 8,606.64,
  the last one taking the rounding residue (8,606.69) so that the principal is
  repaid exactly.
* Two interest methods: the annual rate divided by the number of payments a
  year (a shorter or longer period is counted in days), or the actual days of
  the period over 365.
* The due dates follow the calendar months: a first payment on 15 January
  gives 15 February, 15 March...; a first payment on the last day of a month
  keeps the last day of the months (31 January, 28 or 29 February, 31 March).
* The unpaid lines of the schedule can be changed by hand (due date,
  principal, interest): the balances follow and the last line repays what is
  left. Compute Schedule computes them again from the principal drawn and
  keeps the paid lines.
* Draw the loan down in one or more tranches; each drawdown is posted and the
  unpaid lines are computed again from the principal actually drawn.
* Pay an instalment from its line: the principal, the interest and the
  payment date can be adjusted to what the bank charged.
* Repay early, in part or in full, with the interest due up to the repayment
  date, then choose a shorter term or lower instalments.
* Floating rates: the rate changes on dated rate changes, and the unpaid
  lines from that date are computed again.
* Reclassify at each period end the principal due within 12 months from the
  long-term to the short-term loan account.
* The Loan Report gives per loan, at a date, the outstanding principal, the
  interest accrued since the last due date, the next due date and amount, and
  the principal due within 12 months and after, as a list, a pivot or a PDF.
  Each loan prints with its schedule.
* Loans in a foreign currency.
* Leases: the lease liability at the present value of the lease payments,
  recognized against the right-of-use asset, and each payment billed by the
  lessor on its due date (see Leases below).
* A withholding tax on the interest, such as the 1% of Thailand (P.N.D. 53):
  deducted from what is paid to the lender and booked on the account of the
  tax (see The withholding tax below).
* Record rules per company; the accounting administrators run the loans,
  the accountants and auditors read them, the invoicing users do not see them.

The journal entries
===================

Each action posts one entry, with the lender as partner:

=====================  ==================  ==========================================
Action                 Journal             Entry
=====================  ==================  ==========================================
Drawdown               Bank journal        Dr Outstanding Receipts / Cr Long-term loan
Instalment             Bank journal        Dr Short-term loan, then Long-term loan
                                           (principal) + Dr Interest expense /
                                           Cr Outstanding Payments
Early repayment        Bank journal        as an instalment, with the interest due
Reclassification       Loan journal        Dr Long-term loan / Cr Short-term loan
                                           (or the reverse)
=====================  ==================  ==========================================

For example, 100,000 at 6% over 12 months drawn on 1 January 2025:

* the drawdown posts Dr Outstanding Receipts 100,000.00 / Cr Long-term loan
  100,000.00;
* the first instalment, on 1 February, posts Dr Long-term loan 8,106.64 and
  Dr Interest expense 500.00 / Cr Outstanding Payments 8,606.64;
* a reclassification on 31 January posts Dr Long-term loan 100,000.00 /
  Cr Short-term loan 100,000.00, the whole principal being due within 12
  months; the instalments then repay the short-term account first.

The bank side of the entries
----------------------------

In Odoo 20 the bank account of a bank journal is fed by the bank statement
lines. An entry posted straight on it would add to the bank balance a second
time when the statement line comes in, or be left beside it unreconciled. So
the drawdowns and the payments do what the payments of Odoo do: their bank
leg goes to the outstanding receipts or payments account of the bank journal
(the account of its payment methods, else the outstanding account of the chart
of accounts). When the bank statement line comes in, it is matched with that
outstanding line like a customer or vendor payment, and the outstanding
account goes back to zero.

A company that does not import its bank statements, or uses a cash journal
without statements, can set Post Bank Leg On to Bank Account on the loan: the
bank leg then goes straight to the account of the journal.

How the schedule follows the loan
=================================

The schedule is computed again, keeping the paid lines, after each event:

* Before the first drawdown, the schedule assumes the whole principal is
  drawn on the start date: it is a projection.
* After a drawdown, the unpaid lines repay the principal drawn: the period of
  a tranche counts the old balance up to the drawdown and the new one after it,
  and a new instalment (or principal per period) is computed from the new
  balance over the payments left. The opening balance of a line is the
  principal owed on its due date, the tranches of the period included.
* An early repayment pays the interest due up to its date, so the next line
  only counts the interest from the repayment on. Lower Instalment keeps the
  number of payments and lowers the instalments; Shorter Term keeps them about
  the same and reduces the number of payments to what the next instalment (or
  principal per period) needs to repay the balance. A full repayment closes the
  loan.
* A rate change computes again the unpaid lines due from its date: those
  after it with the rate per period (a period takes the rate in force on its
  first day), those on or after it with the actual days, which split a period
  at the change.
* Changing the rate or the number of payments of a running loan computes the
  unpaid lines again.

Drawdowns and early repayments are dated after the last paid instalment, and
the instalments due on or before an early repayment are paid first. The last
paid instalment and the drawdowns and repayments (latest first) can be
cancelled from the loan: their entry is reversed on its date and the schedule
computed again. These entries cannot be reset to draft or reversed from the
journal entry itself.

The reclassification
--------------------

At a period end, Accounting > Loans > Reclassification posts for each loan the
move that leaves on the short-term account the principal not paid at that date
and due within the next 12 months. What the earlier reclassifications and the
instalments already moved is taken into account, so the reclassification can
be run at every month or year end: it posts only the difference, in either
direction. Reclassify in the order of the dates.

Leases
======

A lease is a contract of the Lease type (Accounting > Loans > Leases),
numbered LEASE/year/0001. Enter the lessor, the lease payment (taxes
excluded), the number of payments, their frequency, the first payment date
(the start date for a lease paid in advance) and the rate of the lease (its
implicit rate, or the incremental borrowing rate of the company). The lease
liability is computed: it is the present value of the payments at that rate,
discounted period by period as the schedule counts the interest, so that the
payments repay it exactly. A lease has a fixed rate and equal payments.

The schedule is the one of the loans: each payment is split into the interest
(the finance charge, on the interest expense account) and the principal (the
reduction of the lease liability); the last payment takes the rounding.

The entries of a lease
----------------------

=====================  ==================  ==========================================
Action                 Journal             Entry
=====================  ==================  ==========================================
Confirmation           Loan journal        Dr Right-of-use asset / Cr Long-term
                                           lease liability, at the present value
Lease payment          Purchase journal    the vendor bill of the lessor: Dr
                                           Short-term, then Long-term lease
                                           liability (principal) + Dr Interest
                                           expense (+ taxes) / Cr Payable
Bill payment           Bank journal        as any vendor bill
Reclassification       Loan journal        as for the loans
=====================  ==================  ==========================================

For example, 12 monthly payments of 1,000.00 in arrears at 6% from
1 January 2025:

* the lease liability is 11,618.93; the confirmation posts on 1 January
  Dr Right-of-use asset 11,618.93 / Cr Long-term lease liability 11,618.93;
* the first payment, due on 1 February, is a bill of the lessor of 1,000.00:
  Dr Long-term lease liability 941.91 and Dr Interest expense 58.09 /
  Cr Payable 1,000.00. The next one repays 946.61 with 53.39 of interest,
  the last one 995.02 with 4.98;
* with the VAT of 7% on the bills and a withholding tax of 1% on the
  interest, the first bill adds Dr VAT 70.00 and Cr Withholding tax 0.58:
  Cr Payable 1,069.42.

Paid in advance (the first payment on the start date), the same lease is
11,677.03: the first payment repays 1,000.00 of liability without interest.

The bills
---------

The Bill button of a lease payment (or Create Bills on the selected
instalments) creates the vendor bill of the lessor, dated on the due date, in
the purchase journal of the lease. A daily scheduled action creates the bills
of the payments due, for the leases set to Bill on the Due Dates. The bills
are posted, or left in draft to check (Lease Bills on the lease); the taxes on
the bills (such as the VAT) go on all the lines, the withholding tax on the
interest line. The bill is then paid like any vendor bill.

The amounts come from the schedule: change the line before billing it. The
bills are in the order of the schedule. The last bill can be cancelled from the
lease, when it is not paid: a posted bill is reversed by a credit note, a draft
one is cancelled. Post the draft bills before reclassifying.

The right-of-use asset is debited on the account of the lease (Right-of-use
Asset Account, from the settings). With Assets Management (om_account_asset)
installed, the module Leases: Right-of-use Assets creates the asset itself
(see below).

A lease is not drawn down nor repaid early, and its terms do not change once
recognized. If its recognition is cancelled (Operations tab), Recognize posts
it again.

The withholding tax
===================

Some countries make the borrower withhold a tax on the interest it pays and
pay it to the tax office: in Thailand, 1% on the interest paid to a company
(P.N.D. 53). Set this tax as the Withholding Tax of the loan or lease: a tax of
the company with a negative amount (-1%), its distribution giving the account
of the tax withheld (and the tax grids). Then:

* the schedule shows on each line the tax withheld on its interest and the
  net payment, the PDF of the loan too, and the Loan Report the tax withheld up
  to its date;
* the payment of an instalment, and of the interest of an early repayment,
  posts Dr Loan + Dr Interest / Cr Withholding tax + Cr Outstanding payments
  for the rest. The withholding line is a tax line of the tax (its account,
  its grids, the interest as its base), and the interest line has the base
  grids, so that the tax reports include it. The tax withheld by the bank can
  be changed when paying;
* the bill of a lease payment has the tax on its interest line: Odoo computes
  it as the other taxes of the bill, and it reduces the amount payable.

For example, the first instalment of the loan above withholds 5.00:
Dr Long-term loan 8,106.64 and Dr Interest expense 500.00 / Cr Withholding tax
5.00 and Cr Outstanding Payments 8,601.64.

The tax is computed by the taxes of Odoo. When a localization defers it to
the payments (the Withholding option of the Withholding Tax module of Odoo, as
in the Thai chart of accounts), the bills leave it to the Pay button of the
bill, as for any bill; the payments of the loans withhold it themselves.

Imported schedules
==================

When the lender gives its own schedule, choose the Imported schedule method
and click Import Schedule. The file is a CSV (comma, semicolon or tab) or an
XLSX file, one row per instalment, a first row of titles being skipped:

* Date, Principal, Interest; or
* Date, Instalment, Interest (the principal is the instalment less the
  interest).

For example, the first rows of the schedule of the loan above::

    Date,Principal,Interest
    2025-02-01,8106.64,500.00
    2025-03-01,8147.17,459.47
    2025-04-01,8187.91,418.73

The dates are 2025-02-01, 01/02/2025 (day first) or in the format of the language of the
user; the amounts 1234.56, 1,234.56 or 1234,56. The import checks the file:
dates increasing, after the start of the loan and its paid instalments,
amounts that are numbers, no negative interest or principal, and principal
adding up to what the loan has to repay (its principal, less the paid
instalments and the early repayments). The unpaid lines are replaced; the
paid ones stay.

The imported lines are then paid, changed by hand and printed as the others.
They are kept as imported when the schedule is computed again: the principal
not drawn yet is assumed drawn on the start date, and an early repayment
comes off the last lines (the loan ends earlier). Import the new schedule of
the lender after an early repayment or a rate change, if it changes the
interest.

Multi-currency
==============

A loan may be in another currency than the company. Its entries are posted in
the currency of the loan with the value in the company currency at the rate of
the entry date. The bank journal must be in the currency of the loan or in the
company currency. The balances in the company currency are not revalued: run
a currency revaluation of the loan accounts if needed.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

In Accounting > Configuration > Settings, in the Loans section, set the
accounts and the journals proposed on new loans: the long-term loan account (a
non-current liability), the short-term loan account (a current liability),
the interest expense account, the loan journal for the reclassifications and
the bank journal for the drawdowns and payments.

For the leases, set the long-term and short-term lease liability accounts
(the loan accounts when empty), the right-of-use asset account and the
purchase journal of the bills.

For a withholding tax, create the tax in Accounting > Configuration > Taxes:
Tax Type Purchases (or None), a negative amount (-1%), the account of the tax
withheld on its distribution.

Check that the payment methods of the bank journal have their outstanding
receipts and payments accounts (Accounting > Configuration > Journals, the
Incoming and Outgoing Payments tabs).

Usage
=====

* Accounting > Loans > Loans: create the loan, check the schedule computed on
  confirmation, then click Draw Down for each tranche.
* Pay the instalments with the Pay button of their line, or from
  Accounting > Loans > Instalments, which lists the instalments to pay of every
  loan.
* Accounting > Loans > Leases: create the lease and confirm it, which
  recognizes it; bill the payments with the Bill button of their line, or let
  the scheduled action bill them on their due dates; pay the bills as any
  vendor bill.
* Early Repayment on the loan repays part or all of the principal.
* For a floating rate, add the rate changes in the Rate Changes tab.
* At each period end, run Accounting > Loans > Reclassification.
* Reporting > Management > Loans shows the position of the loans and of the
  leases at a date (or of one type), and prints it.

Right-of-use assets
===================

With Assets Management (om_account_asset), the module Leases: Right-of-use
Assets (om_account_loan_asset) is installed automatically. Choose a
Right-of-use Asset Category on the lease: on its recognition, the asset
account of the category is debited and the right-of-use asset is created in
that category, at the lease liability (in the company currency), from the
start of the lease, depreciated linearly to the end of the lease term with the
journal, the accounts and the periods of the category, and confirmed when the
category confirms its assets. The asset shows on the lease; cancelling the
recognition cancels it.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
