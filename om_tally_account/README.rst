==========================
Tally Connector Accounting
==========================

The accounting part of Import from Tally (om_tally_connector) for Odoo 20
Community.

Mapping
=======

* The 28 predefined groups of Tally give the account type of their ledgers;
  groups made in Tally inherit the type of their parent.
* Ledgers are linked to an account of the installed chart (matched by name and
  type) or create a new account with a generated code; or they are skipped.
* Sundry Debtors and Sundry Creditors ledgers become partners, matched by
  GSTIN/VAT, then name, phone and email: Link, Create or Skip per line, with
  bulk buttons. Skipped parties post to a partner you choose.
* Bank, Bank OD and Cash ledgers become bank and cash journals.
* Duties & Taxes ledgers are linked to the tax accounts and taxes of Odoo: in
  India CGST, SGST, IGST and cess by rate and use; in the Gulf the VAT of the
  rate (5% United Arab Emirates, 15% Saudi Arabia, 10% Bahrain).
* "Create Odoo Company" makes a company from the details of Tally: name,
  country, currency, tax number, address, and the fiscal year (April to March in
  India, January to December in the Gulf), with the chart of accounts of the
  country when its accounting localization is installed.
* Cost categories and cost centres become analytic plans and accounts.

Importing
=========

* **Opening balances** as on a cut-over date, in one entry dated the day before
  in a dedicated journal. Receivables and payables get one line per open bill
  (reference, date, due date); the difference in opening balances of Tally goes
  to the account you choose. The Stock-in-Hand ledgers stay in the entry unless
  "Leave Stock-in-Hand Out" is set (their amount then goes to the difference
  account).
* **Full history** from the cut-over date, split by period (one financial year
  at a time, Next Period after each one) or read in the background: each
  voucher as an exact journal
  entry, or Sales and Purchase vouchers as invoices and bills (products, taxes,
  cost centres), notes as refunds, receipts and payments posted in their bank or
  cash journal. Bills are reconciled by the references of Tally (New Ref, Agst
  Ref). When the taxes of Odoo do not give the amount of Tally, the voucher is
  posted with the amounts of Tally.
* **Trial balance check** per account before posting (Tally, Odoo after the
  import, already in Odoo), and again after posting.
* Posting runs in batches in the background, each voucher on its own: an error
  marks the voucher only, the rest goes on; Try Again resumes. The mapping table
  makes every step safe to run again.
* **Keep in Sync**: new vouchers read by Alter ID over the direct connection
  are imported; vouchers changed or deleted in Tally after their import are
  flagged, not overwritten.

Tally and TallyPrime are trademarks of their owner, Tally Solutions; this module
is not made, endorsed or supported by Tally Solutions.
