==========
Bank Feeds
==========

Fetch the transactions of your bank accounts automatically into the bank
journals of Odoo 20 Community: connect the bank once through a bank feed
provider, map its accounts to the journals, and the new transactions arrive
every few hours, without duplicates, ready to reconcile.

This module is provider-neutral: each provider is a module of its own. The
first one is **Salt Edge** (``om_account_bank_feed_saltedge``).

Features
========

* **Connections** per company: provider, bank, status (Not Connected,
  Connected, Expiring Soon, Expired, Error), consent expiry date, last sync,
  error message and the bank accounts of the connection.
* **Bank accounts** of the connection: provider account ID, name, IBAN or
  number, currency, balance and balance date given by the bank, the bank
  journal it feeds (one account per journal, in the currency of the account),
  and the first date to fetch (by default the first day of the current month).
  **Create Journal** creates the bank journal of an account.
* **Bank journal**: a Bank Feed section on the journal form (Connect Bank,
  status, last sync, Sync Now, Renew Consent, Disconnect), the status and a
  sync button on the dashboard card, and Connect Bank Feed / Sync Bank Feed in
  the card menu. The journal gets the Bank Feed statements source.
* **Sync** every 4 hours (Sync Every in the settings) and with **Sync Now**:
  the transactions become bank statement lines of the journal, with label,
  amount, partner name, account number, original currency and amount, and the
  transaction as given by the provider in the transaction details.
* **No duplicates**: each line keeps the identifier of the transaction at the
  provider, unique per journal; a transaction already imported is skipped.
  After the first sync, a few days before the last transaction are read again
  for the transactions the bank books late.
* **Booked and pending**: only booked transactions by default. With Import
  Pending Transactions (on the connection), pending ones are imported marked
  as pending, replaced by the booked transaction when it comes, and removed
  when the bank no longer reports them (unless reconciled).
* **Partners**: the partner is set only when it is certain: the one partner
  owning the bank account of the other party, else the one company with
  exactly the name written by the bank.
* **Balance check** after each sync: the balance of the bank against the
  balance of the statement lines of the journal, with a warning on the
  account, the dashboard card and in the log when they differ.
* **Sync logs**: imported, already imported and pending transactions, warnings
  and errors, per account; logs older than 180 days are removed.
* **Consent reminders**: a daily check marks the connections whose consent
  expires within Consent Reminder (Days) (7 by default, per company) and
  schedules an activity for the responsible; an expired consent is marked
  Expired with another activity. **Renew Consent** sends the user to the
  renewal page of the provider and back.
* **Callback** page for the consent pages of the providers: the return URL
  carries a random token valid two hours and used once, the user must be an
  accounting administrator of the company of the connection.
* **Disconnect** removes the connection at the provider; the statement lines
  already imported stay.

Configuration
=============

1. Install a provider module, such as ``om_account_bank_feed_saltedge``, and
   enter your provider keys in Accounting, Configuration, Settings.
2. On a bank journal, click **Connect Bank** (journal form or the menu of the
   dashboard card), choose the provider and the first date to fetch, and give
   your consent on the page of the provider.
3. Back in Odoo, map each bank account of the connection to its journal, or
   click **Create Journal**.
4. Click **Sync Now**. The next transactions come with the scheduled sync.

Accounting, Configuration, Bank Feeds lists the connections and the sync logs.

Security
========

Accounting administrators manage the connections; bookkeepers see them and
can sync. Nothing of Odoo Mates is embedded: each company uses its own
provider account and keys, which the provider modules keep in fields visible
to the administrators only.

Adding a provider
=================

A provider module adds its value to the ``provider`` selection of
``bank.feed.connection`` and overrides, for that value:
``_provider_start_consent``, ``_provider_renew_consent``,
``_provider_handle_callback``, ``_provider_fetch_accounts``,
``_provider_fetch_transactions``, and optionally ``_provider_refresh`` and
``_provider_disconnect``. The docstrings describe the values they return.
Errors are raised as ``BankFeedError``, with ``expired=True`` when the consent
must be renewed.

Support
=======

Odoo Mates, odoomates@gmail.com
