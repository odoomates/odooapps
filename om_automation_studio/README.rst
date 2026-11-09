=================
Automation Studio
=================

Automation Studio adds workflows drawn as flowcharts to Odoo 16. An administrator draws what
happens to the records of a model, step by step, without code: conditions, waits, approvals,
emails, activities, messages and record changes. Each record then goes through the chart, and
the chart shows where it is and the path it took.

Features
========

* A canvas with a palette of steps: drag a step onto the chart, or click it to add it after the
  selected one (on an arrow, it is inserted in the arrow). Draw an arrow by dragging from the
  exit of a step to another step. Pan, zoom, fit, undo and redo, duplicate and delete.
* The Start says when the workflow starts on a record: when it is created, when it is created or
  updated (on chosen fields, and only when a condition becomes true), when a date of the record
  comes, when a button of its form is clicked, or by hand from the Action menu. It filters the
  records, says how many runs a record can have, and can stop a run as soon as a condition is met
  (for instance, the invoice is paid). The chart shows the condition of the Start and of each
  Condition step in words.
* Approval on a button: a Start on a button (Confirm, Post, Validate...) is checked when the button
  is clicked, never when the record is saved. While the approval waits the button does not go on;
  once approved, the next click goes on. An approval covers the values of the fields of the
  condition (and of the watched fields): a change of them asks again at the next click. Only a
  click is checked, never Odoo code calling the same method.
* Logic: Condition (Yes and No exits) and End.
* Waiting: Wait for a time or until a date of the record, Wait Until a condition is met (with an
  optional time limit), and Approval: a user, or the user of a field, approves or rejects, with an
  optional time limit. The approver gets an activity.
* Actions: Update Record (set a value, copy a field, today plus some days, clear), Create Record
  (linked back to the record), Send Email (a template), Schedule Activity and Post Message. Texts
  take placeholders: ``{{ object.name }}``.
* The chart is checked as it is drawn: each step lists what is missing, and a workflow with
  errors cannot be published. A loop with no wait in it is refused.
* Publishing freezes the chart in a version. The runs already started go on with the version
  they started on, so a workflow can be changed safely while records wait in it.
* Runs: every record going through a workflow, the step it is on, when it continues, and its
  steps one by one. Show a run on the chart, open its record, cancel it, or retry the step that
  failed. A step that fails is rolled back and stops its run; it never undoes the change that
  started the run.
* The records of a model with a running workflow get a Workflow Runs entry in their Action menu.
* Approvals show on their record: a banner at the top of the form says who it waits for, with
  Approve and Reject for the approver, and the chatter notes the question and the answer. While it
  waits, the record can be blocked: chosen fields (the status by default, so it cannot be
  confirmed or sent) or any change.
* Automation Studio administrators can answer for the approver, who is told, and the chatter says
  on whose behalf; an Approval step can keep the answer to the approver alone.
* Templates: New opens a gallery of generic workflows that run on any model: approval above a
  limit, approval on a button, follow-up after a status, reminders once a date is passed, reminder before a date, stuck
  in a status, new record response, big value alert, missing information, after completion. Pick
  one and the model, set it (the fields are guessed, and known models such as quotations,
  purchases, invoices and leads come ready), see the chart, and open it in the designer.
* Your templates: Save as Template on a workflow (or in the designer) keeps its chart, for the
  company or for every company; it appears under Your templates when creating a new workflow.
  Automation Studio > Templates exports a template as a file and imports it into another database: users,
  activity types, email templates and the records the steps set are found again by external id or
  name, and those missing are listed on the template and pointed out in the designer.
* Demo data: with demo data, the ready templates of Sales, CRM, Purchase, Invoicing and Contacts
  as draft workflows, for the apps installed, also when installed later. Publish one to try it.

Usage
=====

#. Automation Studio > Workflows > New: pick a template and the model it runs on, or start from
   blank.
#. In the designer, set the Start, add the steps and draw the arrows.
#. Publish. Follow the runs in Automation Studio > Runs, and answer approvals on the record or in
   Automation Studio > Approvals.

Access, in Settings > Users > Automation Studio:

* User: sees the app and the Approvals menu, with their own approvals.
* Supervisor: also follows all the workflows, runs and approvals, cancels and retries runs.
* Administrator: designs, publishes and pauses the workflows, manages the templates, and answers
  any approval for its approver. As with Automation Rules, a workflow changes records with full
  rights: give it to trusted users. The administrator user gets it at install.

Without a group the app is hidden; the approvals asked of a user still come as activities, and are
answered from the banner of the record.

Technical notes
===============

* The Start of the published version becomes an Automation Rule (``base.automation``) whose
  server action, of the type Start Workflow, starts the runs; a manual Start is a server action in
  the Action menu. Pausing a workflow removes them.
* A Start on a button needs neither: ``/web/dataset/call_button`` asks the published workflows of
  the model and method (``_button_gate``) before calling it. A run started by a button keeps the
  values it asks about (``button_values``).
* Waiting runs are continued by the scheduled action "Automation Studio: Continue Waiting Runs" (every
  5 minutes, and at the exact time of a wait).
* A template is a pattern in ``tools/templates.py``: its settings (slots) for a model, and the
  chart it builds from them; ``PRESETS`` holds the settings of known models.
* The demo workflows are created once all modules are loaded (``_register_hook``), as the demo
  data of this module cannot see the apps loaded after it; each app gets them once, so deleted
  ones stay deleted.
* Template files are JSON (``format``, ``version``, ``model``, ``graph``); ``tools/portable.py``
  turns the ids of a chart into references and back. Ids written inside conditions are kept as
  they are.
