===========================
WhatsApp AI Sales Assistant
===========================

Customers chat with your WhatsApp number and an AI assistant answers them from
live Odoo data: products, prices of their price list, stock, quotations built
line by line, delivery methods, the quotation PDF with an online payment link,
order and delivery status, and invoices, optionally after a code sent to the
customer's email. A person takes over at any time from Discuss.

It runs on the AI engine (``om_ai``: your own provider and key, or a local
model; usage log and daily limits) and on the WhatsApp Connector Base
(``om_whatsapp_base``), so it works with every WhatsApp provider of the
connector: the Meta Cloud API (``om_whatsapp``), the QR device
(``om_whatsapp_device``) and WhatsApp Web (``om_whatsapp_web``).

How it works
============

* A message arrives on a WhatsApp account with the assistant switched on. The
  webhook of the provider only queues a job; a scheduled action answers it, so
  receiving never waits for the AI.
* The assistant reads the last messages of the conversation, the customer and
  the instructions of the account, calls its tools and answers in the language
  of the customer. Everything stays in the WhatsApp conversation in Discuss.
* It works as the *WhatsApp Assistant* user of the company, made when the
  assistant is switched on: no password, nobody logs in with it. Its group
  gives Sales / Own Documents and the reading the tools need. It never
  confirms an order nor posts an invoice: the code refuses it.

Who is the customer
===================

The level of a customer is computed by the code from the conversation, never
by the AI, and every tool declares the level it needs:

* **0 Unknown**: a number without a contact, or on several contacts. General
  questions only: products, public prices, in stock or not, the knowledge text
  of the account.
* **1 Known number**: the number is on exactly one contact, or the contact was
  made in this conversation. Own quotations, payment links, order and delivery
  status.
* **2 Private data**: invoices, open balance, invoice payment links, addresses.
  By default a known number reaches them directly. With the account setting
  *Email Code for Private Data*, the customer first types a 6-digit code mailed
  to the email already on their contact: the number stays verified 30 days
  (setting), 3 wrong codes lock it for one hour, and a contact without an email
  goes to a person. Staff can tick or untick *WhatsApp Verified* on the contact
  in both modes; each verification is logged in the chatter of the contact.

Tools take the customer from the conversation, never from what the AI sends,
so a customer cannot see the orders or invoices of anyone else. A customer sees
their own documents, or those of their whole company (setting).

Ordering
========

1. The customer asks for products; the assistant answers with prices of the
   customer's price list and the stock (numbered lists to answer with a
   number).
2. The first item makes a draft quotation; the next ones change it. When the
   stock is short the assistant offers what is available ("only 2 available,
   add 2?").
3. A new customer is not asked to register: before the first item the
   assistant asks the name of the order and offers the WhatsApp profile name
   ("Shall I put the order under Steve Miller?"). The contact gets the WhatsApp
   number as phone and the tag *Created from WhatsApp*.
4. Delivery address (text or location pin, read back to the customer), the
   delivery method among those of the account with its price, an optional
   email.
5. A summary written by the code (lines, delivery, taxes, total, address); the
   customer replies YES.
6. The quotation PDF and the standard online payment link of Odoo are sent.
   The payment confirms the order, the usual way, and the customer gets a
   confirmation on WhatsApp. One reminder goes when the link is still unpaid
   after the hours set on the account. There is no cash on delivery.

The salesperson of each quotation is the customer's salesperson, else the
default salesperson of the account; they are mentioned in the chatter of the
quotation, which says the assistant made it.

Settings per WhatsApp account
=============================

Assistant on or off, persona and instructions, knowledge text (opening hours,
delivery areas, policies), enabled tools, default salesperson, delivery
methods offered, payment reminder hours, working hours (the assistant answers
always, or only outside the working hours), hand-over words, replies per day
and per customer, the email code for private data with its validity, and
whether private data covers the whole company. The
*Check Setup* button tells what still keeps the assistant from answering.

Hand-over and opt-out
=====================

* The customer writes a hand-over word ("human", "person"...), the AI is
  unsure or cannot help, a daily limit is reached, or the AI fails: the
  conversation goes to the salesperson, who is added to it and notified, and
  the assistant stops answering.
* In Discuss, *Take Over from the AI Assistant* and *Give Back to the AI
  Assistant* switch it in one click; a user who writes to the customer takes
  over too.
* STOP opts the number out (exclusion list of Odoo) and START opts it in
  again.

Reports
=======

WhatsApp > AI Assistant > Analysis: conversations, AI replies, hand-overs,
quotations and orders made, revenue of the confirmed orders, AI cost and tokens
per conversation (from the usage log of the AI engine).

Setup
=====

1. Set an AI provider and a chat model in Settings > AI (``om_ai``).
2. Enable online payment with a payment provider.
3. In WhatsApp > Configuration > Accounts, switch *AI Assistant* on, fill the
   *AI Assistant* tab and click *Check Setup*.

The provider must send by itself (Meta Cloud API, QR device). With WhatsApp
Web the answers go through the browser of the user who has WhatsApp Web open
with the extension; when nobody has it open, they wait in the conversation to
be sent again.

Limits
======

* Product photos sent by customers are kept in the conversation but not
  recognised.
* Interactive list messages are not used: product choices are numbered lists,
  which every provider can send.
* Tracking links show when a carrier connector fills the tracking reference of
  the delivery; no shipping message is sent by itself.

Author
======

Odoo Mates
