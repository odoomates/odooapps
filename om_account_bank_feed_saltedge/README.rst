=====================
Bank Feeds: Salt Edge
=====================

Salt Edge provider for Odoo Mates Bank Feeds (``om_account_bank_feed``):
connect the banks supported by Salt Edge through your own Salt Edge account,
with the Account Information API version 6, and fetch their transactions into
the bank journals of Odoo 20 Community.

Features
========

* **Settings** per company: App ID, Secret and an optional RSA private key,
  in fields hidden like passwords and visible to the administrators only.
  **Test Connection** checks the keys.
* **Request signing**: when the private key is set, every request carries the
  ``Expires-at`` and ``Signature`` headers (RSA SHA256 of
  ``Expires-at|method|URL|body``), which Salt Edge requires for the
  applications in Live status.
* **Customer**: the Salt Edge customer of the company is created at the first
  connection (``POST /customers``).
* **Connect**: a connect session (``POST /connections/connect``) with the
  consent scopes accounts and transactions, from the chosen date, automatic
  refresh, and the return to the callback page of Odoo, which receives the
  ``connection_id`` (or ``error_class``).
* **Connection**: the bank name and the status (``GET /connections/{id}``) and
  the expiry date of the active consent (``GET /consents``).
* **Accounts** (``GET /accounts``): name, IBAN or number, currency, balance.
* **Transactions** (``GET /transactions``): booked transactions read page
  after page with ``from_id``, continuing from the last one read, and pending
  transactions (``pending=true``); duplicated transactions marked by Salt Edge
  are skipped. Payer or payee, counterparty account number, original amount
  and currency, and the whole transaction are kept on the statement line.
* **Refresh**: before each sync, a background refresh is asked when Salt Edge
  allows it (``next_refresh_possible_at``); its data comes at the next sync.
* **Renew**: Renew Consent opens a reconnect session
  (``POST /connections/{id}/reconnect``).
* **Disconnect** removes the connection at Salt Edge
  (``DELETE /connections/{id}``).
* **Errors**: the class and message of Salt Edge on the connection and in the
  sync log; an expired or revoked consent marks the connection Expired; HTTP
  429 is retried a few times after the wait Salt Edge asks for.
* **Test banks**: Offer the test banks of Salt Edge (``include_sandboxes``).

Configuration
=============

1. Create an application in your Salt Edge account and copy its App ID and
   Secret from the API keys page of its dashboard. Applications in Test or
   Pending status see the fake banks of Salt Edge (country XF, for example
   ``fakebank_simple_xf``) to try the whole flow with their own keys.
   Applications in Live status
   must sign their requests: generate an RSA key pair, add the public key to
   your Salt Edge dashboard and paste the private key in Odoo.
2. In Accounting, Configuration, Settings, Salt Edge: enter the App ID, the
   Secret and, for Live, the private key. Click **Test Connection**.
3. On a bank journal, click **Connect Bank**, choose Salt Edge and continue to
   the Salt Edge page; choose the bank and give your consent. Back in Odoo,
   map the accounts to the journals and click **Sync Now**.

The API address is ``https://www.saltedge.com/api/v6``. The system parameter
``om_account_bank_feed_saltedge.api_url`` replaces it, for a proxy or a test
server.

What was verified
=================

The requests and answers follow the public Salt Edge documentation
(https://docs.saltedge.com/v6/ and https://docs.saltedge.com/v6/api_reference):
authentication and signature, pagination, errors and rate limits, customers,
connect, reconnect, background refresh, connections, consents, accounts and
transactions. No real Salt Edge account was used: every flow was tested end to
end against a local server answering with the documented samples (connect from
a bank journal, consent page and return, account mapping, first sync, a second
sync without duplicates, a pending transaction then booked, a balance
mismatch, consent expiry reminder and renewal, expired consent, refused keys,
HTTP 429, signed requests, disconnect, reconciliation of a synced line), not
against the live Salt Edge API. Before going live, check the flow with your
own application in Test status and a fake bank.

Salt Edge is a trademark of its owner. This module is made by Odoo Mates and is
not affiliated with or endorsed by Salt Edge.

Support
=======

Odoo Mates, odoomates@gmail.com
