=======================================
AI Fields - Fill Fields with Your Own AI
=======================================

Let the AI fill fields of any model, with your own AI provider or a local
model set up in the AI engine (``om_ai``). No key or service of Odoo Mates is
used.

AI fields
=========

*AI > Configuration > AI Fields*: pick a model and a field, or create a new
field, and write the prompt.

* **Field types**: one-line text, long text, formatted text (HTML), selection,
  link to a record (many2one, chosen by name), checkbox, number (float,
  integer, monetary).
* **New fields**: give a label, a technical name (``x_...``) and a type
  (selection values or the linked model when needed), then click **Create
  Field**. The field is added to the model and shown on its form (in an *AI*
  tab when the form has a notebook).
* **Prompt with record values**: ``{{ name }}``, ``{{ partner_id.name }}``,
  ``{{ order_line.product_id }}``... Values are written as text (names of linked
  records, labels of selections, plain text of HTML). Nothing in the prompt is
  evaluated as code, and only fields the user may read are filled in.
* **Valid values only**: the AI answers with JSON following a schema built from
  the field. Selections accept only their values, many2one fields only the
  names of the allowed records (a filter on the records it may choose from),
  numbers only numbers. Invalid answers are not written and are reported.
* **Per field**: the purpose (fast or chat model) or a specific model, extra
  instructions, a filter on the records to fill, whether existing values are
  replaced, and a number of records per day.

When
====

* **On demand**: *Fill ... with AI* in the Actions menu of the list and the
  form (several records at once; more than 10 records are queued).
* **When fields change**: on create, or when one of the trigger fields
  changes, the record is queued and filled in the background, so saving never
  waits for the AI. This uses an automation rule created for the AI field.
* **Scheduled**: a scheduled action queues the records whose field is still
  empty, a set number per run.

The queue (*AI > Configuration > AI Field Queue*) shows pending, done and
failed records with the error, and failed ones can be retried. Records are
filled as the user who triggered them, so access rights apply; the AI call is
allowed for every user who edits such records and is logged under that user
in the AI usage, feature ``fields``, within the daily limits of the AI
settings.

Server action "Update Fields with AI"
=====================================

A new server action type for automation rules and contextual actions: choose
the fields to fill (several at once), write the prompt with record values,
the purpose or model, and whether to replace existing values. In automation
rules the records are always filled in the background.

Example: an automation rule on leads, *On create*, with the action *Update
Fields with AI* filling the priority (selection) and the tags from the
description.

Configuration
=============

#. Set up a provider and the default models in the AI engine.
#. Create an AI field, try it with **Try on One Record**, then turn on the
   triggers you need.

Limits
======

* Many2one fields list at most 200 allowed records to the AI; with more
  records, the name given by the AI must match one record.
* Dates, many2many and one2many fields are not filled.
* The No Code Customizer (om_pen) has no AI field shortcut yet: create the AI
  field here on the field made with it.
* Check the results with your own provider and model before you rely on them.

Credits
=======

Author: Odoo Mates
