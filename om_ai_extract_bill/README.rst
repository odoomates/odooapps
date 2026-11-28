=================================================
AI Vendor Bill Reading - Bill OCR with Your Own AI
=================================================

Adds an AI engine to Vendor Bill OCR (``om_account_bill_ocr``), with your own
AI provider or a local model of the AI engine.

* *Settings > Invoicing > Vendor Bill OCR*: **Engine** *On Your Server* (as
  before) or *With Your AI Model*, and whether to fall back on the server
  reading when the AI fails or a limit is reached.
* With the AI engine, uploaded bills (and the **Read the Bill** button) are
  read by the chat model from the text of the PDF, or by the vision model for
  scans and photos.
* The rest works as in Vendor Bill OCR: the vendor is recognized by its tax
  number, bank account, email or name, the account and the taxes come from
  what earlier bills taught, a bank account the vendor never gave is flagged,
  and the bill stays a draft with the fields to check.
* The lines are kept only when they add up to the untaxed amount; untaxed
  amount plus taxes must give the total. The confidence and the flags of the
  AI are posted on the bill, and a low confidence or a flag marks the bill
  *Read, To Check*.
* Usage is logged under the feature ``extract``.

Credits
=======

Author: Odoo Mates
