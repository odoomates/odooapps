## Module <om_account_bank_statement_import>

#### 02.11.2026
#### Version 1.0.2
##### IMP
- the statement lines keep the foreign amount and the foreign currency of a transaction made in another
  currency than the one of the account: from the new columns of the CSV and Excel file maps, the
  instructed or transaction amount of CAMT, the /OCMT/ of MT940 and the CURRENCY or ORIGCURRENCY of OFX
- a file with a foreign amount in an inactive or unknown currency is now refused with a message: activate
  the currency, or correct its code, then import the file again

#### 30.10.2026
#### Version 1.0.1
##### IMP
- the statements are imported in the credit card journals too, as in the bank journals

#### 18.09.2026
#### Version 1.0.0
##### ADD
- initial release: import the bank statements in CAMT.053, MT940, OFX, QFX, QIF, CSV and Excel,
  with a map of the columns for the CSV and Excel files of each bank
- the journal is recognised from the account number in the file and the transactions already
  imported are left out
