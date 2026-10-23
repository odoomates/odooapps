=======================
WhatsApp Connector Meta
=======================

This module connects Odoo 17 to the official WhatsApp Cloud API of Meta. Messages, PDFs and template
messages go out from the server: from the composer, the chatter, Discuss and automation rules, for any
number of records, with no browser open. Replies, files, statuses and reactions come in through the
webhook of the app, into the WhatsApp conversations of Discuss and the chatter of the documents. It is
a provider of WhatsApp Connector Base (``om_whatsapp_base``).

Features
========

* Connect in three values: the App ID, App Secret and access token of the app of the company in Meta
  for Developers. Odoo finds the WhatsApp business accounts and numbers of the token, registers the
  chosen number, sets the webhook of the app on itself, and sends a test message.
* Check Connection: the token, the number (quality rating, messaging limit) and the webhook, at any time.
* Text, documents, pictures, videos and audio, with the text as the caption of the first file.
* The webhook, signed by Meta with the App Secret: messages (text, files, locations, buttons), the
  sent, delivered, read and failed statuses with the reason of Meta, and reactions.
* Automation rules and scheduled actions queue their messages; the scheduled action WhatsApp: send
  the queue of Meta sends them, so that confirming an order never waits for Meta.
* The 24 hours of Meta: free text, from the composer or a conversation of Discuss, within 24 hours of
  the last message of the number; after, the conversation says so, and an approved template goes. The
  header of the conversation counts down the time left, and says Templates only once it is over.
* Templates approved by Meta: the fields of the body ({{ object.partner_id.name }}) become {{1}},
  {{2}}... with samples for the review, the report the PDF at the top. Submit to Meta, then the status
  (in review, approved, rejected with the reason) comes by itself. Changing the field behind a number
  keeps the approval; changing the text asks for a new one. The preview under the text shows the
  samples given to Meta and the footer.
* The templates made in Meta come to Odoo by themselves: when Meta tells their status through the
  webhook, and once a day (scheduled action WhatsApp: sync the templates of Meta). Sync Templates on
  the account brings them at once. They come archived until their fields are set in place of
  {{ '1' }}, {{ '2' }}...

Configuration
=============

In WhatsApp > Configuration > Accounts, create an account with the provider Meta, save it, and click
Connect to Meta. The assistant has one task a page, with its progress across the top, a button to the
right page of Meta and a drawing of where the value is on it. It checks each value as soon as it is
pasted, and ends on a summary of the number: quality, daily limit, token, and what was set up:

1. Create your app in Meta for Developers (use case: connect with customers through WhatsApp), in
   the business portfolio of your company in Meta Business Suite (create one first if you have none).
   Meta makes the WhatsApp business account and its free test number with the app.
2. Copy its App ID.
3. Copy its App Secret (settings of the app).
4. Get a token from the Graph API Explorer of Meta (your app, a user token with the permissions
   whatsapp_business_management and whatsapp_business_messaging), and add your own number to the
   recipients of the test number (WhatsApp > API Setup > To).

When Meta does not say which WhatsApp account the token is for (a token not limited to some accounts),
the assistant asks for the WhatsApp Business Account ID, shown on the API Setup page under the number.

Odoo then finds the number (Meta gives a free test number), registers it, has Meta send the messages
to this Odoo, and sends you a test message. The temporary token works 24 hours: Make it Permanent, on
the account, guides you to the token of a system user, which never expires.

Meta sends the webhook to a public https address only: a hosted Odoo has one; a local Odoo needs a
tunnel (ngrok, cloudflared), set as its web.base.url, with web.base.url.freeze set to True. Meta calls
without a session: on a server with several databases, Odoo must find this one alone, with a dbfilter
(or db_name) that keeps it for that address. The assistant and Check Connection tell when it does not.

Automation rules are not installed with this module: to send, for example, the quotation when an order
is confirmed, install the Automation Rules app and set up the rule as described in the README of the
base module, with an approved template.

The Graph API version is v23.0; the system parameter ``om_whatsapp.graph_version`` moves to a newer one.

Credits
=======

Contributors
------------

* Odoo Mates <odoomates@gmail.com>

Author & Maintainer
-------------------

This module is maintained by the Odoo Mates
