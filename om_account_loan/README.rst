=====
Loans
=====

This module manages the loans a company receives from banks and other lenders
in Odoo 20 Community Edition: the contract, its amortization schedule, the
drawdowns, the instalments, the early repayments, the floating rates, the
current and non-current reclassification and a loan report.

Features
========

* Record a loan: the lender and its reference, the principal, the currency,
  the start date, the first payment date, the number of payments and their
  frequency (monthly, quarterly, semi-annual or annual), a fixed or floating
  annual rate, the accounts and the journals. Loans are numbered LOAN/year/0001
  and move from Draft to Running, then Closed (or Cancelled).
* Two schedule methods: equal instalments (annuity) or fixed principal.
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

For example, 100,000 at 6% over 12 months drawn on 1 January:

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
* Early Repayment on the loan repays part or all of the principal.
* For a floating rate, add the rate changes in the Rate Changes tab.
* At each period end, run Accounting > Loans > Reclassification.
* Reporting > Management > Loans shows the position of the loans at a date,
  and prints it.

Coming next
===========

Leases (the schedule with the vendor bills of the lessor and the right-of-use
asset), the withholding tax on the interest and the import of a schedule given
by the lender.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
