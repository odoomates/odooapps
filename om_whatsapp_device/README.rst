=====================
WhatsApp Connector QR
=====================

This module links the WhatsApp of a company to Odoo 20 with a QR code, as WhatsApp Web is linked: the
account is a linked device of the phone. Messages, PDFs and the replies then go and come from the
server, without a browser open, through the WhatsApp Bridge of the module, a small Node.js program on
the server of Odoo. It is a provider of WhatsApp Connector Base (``om_whatsapp_base``).

Features
========

* Link in a minute: Link WhatsApp shows the QR code, live; scan it from WhatsApp › Linked devices on the
  phone, or link with a code typed on the phone.
* Send from the composer, the chatter, Discuss and automation rules, with files; the replies, files,
  voice messages, ticks and reactions come to the conversations of Discuss and the chatter of the
  documents.
* As a person sends: one message at a time, typing first, a random pause between two, a number of
  messages a day. Automation rules wait in a queue.
* Start the Bridge from Odoo, or run it as a service of the server (systemd, Docker); Odoo checks it
  every 5 minutes, and tells when the phone unlinked it.

It needs a server where Node.js runs next to Odoo: on premise or a VPS, not Odoo Online.

This is not the official API of WhatsApp: WhatsApp may ban a number that sends too much, too fast, or to
people who did not ask for it. For campaigns, use the official Cloud API of Meta (``om_whatsapp``, coming soon).

Installation
============

1. On the server of Odoo, install Node.js 20 or later. The ``nodejs`` of Ubuntu 24.04 is 18, too old:
   take it from NodeSource::

       sudo apt remove -y nodejs npm
       curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
       sudo apt install -y nodejs
       node --version

   Odoo runs the ``node`` it finds in its ``PATH``; another one (nvm, ...) goes in the system parameter
   ``om_whatsapp_device.node``, with its full path.

2. Install the packages of the bridge, once, and again after each update of the module::

       cd /path/to/om_whatsapp_device/bridge
       npm ci
       npm test

3. Add the folder of the module to the ``addons_path`` of Odoo, restart Odoo, update the Apps list and
   install **WhatsApp Connector QR**; it brings WhatsApp Connector Base.

Configuration
=============

1. WhatsApp › Configuration › Accounts › New: a name, the provider **WhatsApp QR (Linked Device)**, the
   users who answer; save. The form shows these steps until the account is linked.
2. Run the WhatsApp Bridge. Either:

   * **Start the Bridge** on the account (administrators): Odoo starts it, and starts it again when it
     finds it stopped (every 5 minutes); its log is in ``<data_dir>/om_whatsapp_bridge/bridge.log``.
   * Or as a service of the server, sturdier: systemd or Docker, with the secret of the tab
     *WhatsApp QR* in ``OM_WA_SECRET`` (see ``bridge/README.md``).

3. Click **Link WhatsApp**: the QR code shows, live, and changes every few seconds.
4. On the phone: WhatsApp › Settings (or ⋮) › **Linked devices** › **Link a device**, and scan the
   code. No camera at hand: *Link with a phone number instead*, and type the code shown on the phone.
5. The account turns **Linked**: send from a contact, a document or Discuss.

On the tab *WhatsApp QR*: the number of messages a day and the pause between two.

Good to know:

* The bridge listens on ``127.0.0.1:8077``; when Odoo is not on ``http://127.0.0.1:<http_port>``, set
  its address in the system parameter ``om_whatsapp_device.odoo_url``.
* Odoo checks the bridge, and fetches the profile pictures of the customers without a photo, with
  scheduled actions: run Odoo with cron threads (not ``--max-cron-threads=0``).
* On a server of several databases, the bridge names its database itself: no dbfilter is needed.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
