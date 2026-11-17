==============
Connector Base
==============

The common engine of the Odoo Mates connectors to shops and marketplaces (the Shopify Connector, and the
next ones). It has nothing to set up: the connectors that need it install it.

Features
========

* **Job queue**: every import, export and webhook of a connector is a job, run by the scheduled action
  *Connectors: run the jobs*. Two workers never run the same job (row locking).
* **Retries**: a job that fails leaves no change and is tried again after 2, 4, 8 minutes and more, up to its
  number of attempts; an error of the user (``UserError``) fails it at once. The connection gets told of the
  jobs that fail for good.
* **No duplicates**: the jobs of a connection with the same key make one job, with the newest data.
* **Mappings**: an abstract model links an external ID to an Odoo record, once per connection.
* **Order workflows**: confirm an imported order, create and post its invoice, register one or several
  payments, pay back its credit notes.
* **Secrets**: helpers to store access tokens and secrets encrypted (key: the ``om_connector_key`` option of
  the Odoo configuration file, else the secret of the database).
* **Webhooks and HTTP**: HMAC-SHA256 signatures checked in constant time, and HTTP calls that wait and try
  again on rate limits, server and network errors.

Jobs: Settings > Technical > Connectors > Jobs, and the menu of each connector. Done jobs are removed after
30 days (system parameter ``om_connector_base.job_keep_days``).

For developers
==============

* A connection inherits ``om.connector.backend.mixin`` and queues work with
  ``self._connector_enqueue('_connector_job_import_order', payload, dedupe_key='order:42')``; the method gets
  the job and reads ``job.payload`` and ``job.backend``.
* A mapping inherits ``om.connector.binding.mixin`` (``_connector_find``, ``_connector_bind``).
* ``RetryableJobError(message, delay=60)`` tries a job again later.
