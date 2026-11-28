=========================================================
AI Live Chat Agent - Your Own AI Answers Website Visitors
=========================================================

An AI agent answers the visitors of your website live chat, with your own AI
provider or a local model set up in the AI engine (``om_ai``). No key or
service of Odoo Mates is used.

Agents
======

*Live Chat > Configuration > AI Agent > Agents*: give the agent a name and a
picture (the visitors see them), instructions (tone, topics), the purpose or
the model, and its knowledge. Then choose the agent on a live chat channel
(tab *AI Agent*): it answers **always** (operators take over when needed) or
**only when no operator is available**.

Knowledge
=========

*Live Chat > Configuration > AI Agent > Knowledge*:

* **Text**: anything the agent should know.
* **FAQ**: questions and answers.
* **Website pages**: the texts of the chosen pages, read again every day.
* **Products** (with a sales app): names, categories and descriptions of the
  published products, read again every day.

Sources are cut into parts. For each question, the best parts are found by
Postgres full-text search, or by meaning with the embeddings model of the AI
settings (*Search by Meaning*), and given to the AI with the question.

Tools
=====

* **Product search** (with a sales app): the current list price, the currency
  and whether the product is in stock (with Inventory, optionally the
  quantity).
* **Create a lead** (with CRM): with the contact details the visitor gives
  and the transcript, linked to the chat.
* **Create a helpdesk ticket** (with Odoo Mates Helpdesk): with the email of
  the visitor and the transcript; the ticket number is given to the visitor.
* **Hand over to an operator**.

The tools only appear when the apps are installed; nothing else is needed.

Hand-over
=========

The chat goes to an operator of the channel who is online:

* when the visitor writes one of the hand-over words (human, operator...),
* when the agent is not sure (the knowledge and the tools do not answer),
* when the answer limit of the chat is reached or the AI fails.

Operator hours can be set (time zone, from/to, Monday to Friday). Outside
them, or when nobody is online, the visitor gets your message and the agent
goes on, so it can still take the visitor's email for a lead or a ticket.
Once an operator joined, the agent stops answering in that chat.

Safety
======

* The agent is told to answer from the knowledge and the tools only.
* **Never an invented price**: any amount with a currency in an answer that
  was not returned by a tool or written in the knowledge is not sent; the
  visitor is told the price will be checked and the chat is handed over.
* Answers are computed in the background with a typing indicator: the
  visitor's message is saved at once.
* Limits: answers per chat, messages per visitor per hour, characters per
  message, and the token and cost limits of the AI settings.
* Every call is logged in the AI usage, feature ``livechat``. *Answers* lists
  each answer with the knowledge parts and the tools used.

Limits
======

* Prices are the list prices of the products, not pricelist or customer
  prices.
* Website pages are read from their saved content; texts built by code at
  display time are not read.
* Check the answers with your own provider and model before you rely on them.

Credits
=======

Author: Odoo Mates
