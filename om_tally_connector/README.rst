=================
Import from Tally
=================

Moves a Tally company into Odoo 20 Community: the chart of accounts, the parties,
the opening balances with the open bills, the full voucher history and the stock,
with a trial balance check before anything is posted. Installs Tally Connector
Base, Tally Connector Accounting and Tally Connector Inventory together.

Steps
=====

#. **Connect**: Tally Import > Imports > New. Upload the XML files exported from
   Tally, or connect to Tally on its port. Check the Tally country (India, United
   Arab Emirates, Saudi Arabia, Bahrain or other): it sets the tax number (GSTIN
   or TRN), the taxes matched and the fiscal year of a new Odoo company, which
   "Create Odoo Company" makes from the details of Tally. The "Load Sample Files"
   button attaches a sample export to try everything first.
#. **What to import**: the opening balances on the cut-over date with the open
   bills (recommended: the books start clean, older years stay in Tally), or the
   full history, in one of two ways:

   * **Split by period**: one financial year (or any period) at a time: set the
     period, read it (with files: the export of that period), check and post it,
     then Next Period. Each run adds to the previous ones, nothing is doubled,
     and the periods done are listed.
   * **Read in the background**: a background job reads one file, or one month
     of Tally, at a time, with a progress bar; it resumes where it stopped. Big
     files are read piece by piece, never whole in memory.
#. **Analyze**: Read & Analyze reads the masters and vouchers into staging
   tables and shows the counts per voucher type and year, the books beginning
   date, the difference in opening balances and the problems found.
#. **Map**: Propose Mapping matches the ledgers with the chart of accounts, the
   parties with the partners, the stock items with the products. Change any
   line, then Create & Link.
#. **Check**: the trial balance of Tally next to what Odoo will hold, per
   account. Posting waits until every difference is explained, or accepted to a
   suspense account.
#. **Post**: the opening entry first, then the vouchers in batches in the
   background, with the progress and the errors per voucher.
#. **Verify**: the trial balance of Tally against the posted entries; then set
   the lock date.

Exporting from Tally
====================

* Masters: Display More Reports > List of Accounts, Alt+E Export, format XML,
  all masters.
* Vouchers: Day Book for the period (F2 to set it), Alt+E Export, format XML.
* For the full history split by period, export the Day Book of one period per
  file.
* Direct connection: in TallyPrime, F1 Help > Settings > Connectivity,
  "Client/Server configuration": TallyPrime acts as Server or Both, port 9000,
  with the company open. Odoo must reach the computer of Tally on the network.

What was checked against a real Tally
=====================================

Nothing yet. The connector was built from the XML formats documented by Tally
Solutions and tested with the sample export shipped in om_tally_base
(data/sample) and with a local imitation of the HTTP server of Tally. Before
using it on real data, check on a Windows computer with TallyPrime or Tally.ERP 9:

* an XML export of the masters and of the Day Book (UTF-16 and ASCII) is read
  with the right counts, and the opening balances add up as in Tally;
* the direct connection lists the companies and reads masters and vouchers
  (the "List of Accounts" and "Day Book" requests, and the collection requests
  for the companies and the changes by Alter ID);
* the GST details of the parties (GSTIN, state) and of the stock items (HSN,
  rate) in your version of Tally; for the Gulf editions, the TRN of the parties
  and the VAT ledgers;
* vouchers in foreign currency and vouchers in invoice mode with discounts.

Trademarks
==========

Tally and TallyPrime are trademarks of their owner, Tally Solutions. This module
is made by Odoo Mates; it is not made, endorsed or supported by Tally Solutions.
The names are used only to say which data the module reads.
