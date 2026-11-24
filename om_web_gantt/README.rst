==========
Gantt View
==========

A ``gantt`` view type for Odoo 20 Community. Records are shown on a timeline,
grouped in rows, and planned with the mouse: drag a pill to move it (also to
another row), drag its edges to change the start or the end, click an empty
cell to create a record there.

The module only depends on ``web``. It ships no view on other apps: it is a
base for planning, rental, field service, manufacturing or project apps, which
add a ``<gantt>`` view to their own models.

Features
========

* Day, week, month and year scales, with previous / today / next and a date
  picker.
* Rows and sub-rows from the group by of the search panel (or
  ``default_group_by``), with folding, avatars and totals.
* Grouping by a many2many field: a record shows in the row of each of its
  values, records without value go to an "empty" row with a label of your
  choice; moving a pill to another row replaces that value.
* Drag and drop to move, resize to change the dates, snapping to the
  precision of the scale.
* Click (or drag over) empty cells to create a record with the dates and the
  values of the row filled in; "plan existing" picks records without dates.
* Popover on click with Edit and Delete, from a QWeb template of your own.
* Colour from a field, progress bar, today line, weekends shaded.
* Consolidation: the sum of a field per column, red over a maximum, and a
  total row.
* Dependency arrows from a many2many field (red when the order is broken).
* Non-working periods greyed per row through a model hook.
* Progress bar in the row headers (capacity) through a model hook.
* Pill decorations (``decoration-warning``, ``decoration-striped``...) like
  list views.
* Access rights respected: no drag, resize or create when the user cannot
  write or create.

Arch reference
==============

.. code-block:: xml

    <record id="project_task_view_gantt" model="ir.ui.view">
        <field name="name">project.task.gantt</field>
        <field name="model">project.task</field>
        <field name="arch" type="xml">
            <gantt string="Planning"
                   date_start="planned_date_begin"
                   date_stop="date_deadline"
                   default_scale="week"
                   scales="day,week,month"
                   default_group_by="user_ids"
                   color="color"
                   progress="progress"
                   consolidation="allocated_hours"
                   consolidation_max="{'user_ids': 8}"
                   thumbnails="{'user_ids': 'avatar_128'}"
                   dependency_field="depend_on_ids"
                   progress_bar="user_ids"
                   empty_row_labels="{'user_ids': 'Open Tasks'}"
                   decoration-striped="state == 'draft'"
                   display_unavailability="1"
                   total_row="1">
                <field name="project_id"/>
                <field name="stage_id"/>
                <templates>
                    <t t-name="gantt-popover">
                        <div><strong>Project: </strong><field name="project_id"/></div>
                        <div><strong>Stage: </strong><field name="stage_id"/></div>
                    </t>
                </templates>
            </gantt>
        </field>
    </record>

Add ``gantt`` to the ``view_mode`` of the action.

Attributes of ``<gantt>``
-------------------------

``date_start``, ``date_stop`` (required)
    Date or datetime fields of the start and the end. With date fields the end
    day is included.

``string``
    Title of the view (shown in the corner when the view is not grouped).

``default_scale``
    ``day``, ``week``, ``month`` (default) or ``year``.

``scales``
    Comma-separated list of the scales offered in the scale menu.

``precision``
    Snapping of drag and resize per scale, e.g.
    ``{'day': 'hour:quarter', 'week': 'day:half', 'month': 'day:full', 'year': 'month:half'}``.
    Values: ``hour:full|half|quarter`` (day), ``day:full|half`` (week, month),
    ``month:full|half`` (year). Default: half hours, half days, full months.

``default_group_by``
    Comma-separated fields used for the rows when the search has no group by.

``default_order``
    Order of the records, e.g. ``"priority desc, planned_date_begin"``.

``color``
    Field giving the colour of the pills: an integer colour index (0-11, as in
    kanban) or a many2one (one colour per record of the comodel).

``progress``
    Numeric field from 0 to 100 drawn as a progress bar in the pill.

``pill_label``
    ``1`` to add the dates to the label of the pills.

``create``, ``edit``, ``delete``
    ``0`` to forbid creating (no New button, no cell buttons), editing (no
    drag and drop, no resize) or deleting from the view. Access rights are
    always checked as well.

``plan``
    ``0`` to hide the "plan existing" button of the cells (it opens a list of
    the records without dates and plans the selected ones in the cell).

``form_view_id``
    Form view used to create and open records.

``consolidation``
    Numeric field summed per column: in group rows, in a strip under the
    pills, in the row header (total of the period) and in the total row.

``consolidation_max``
    Dictionary ``{groupby_field: maximum}``: a column of a row grouped by that
    field turns red when its sum is above the maximum.

``total_row``
    ``1`` to add a total row (count of records, or sum of ``consolidation``).

``thumbnails``
    Dictionary ``{groupby_field: image_field}``: avatar of the rows grouped by
    a relational field, e.g. ``{'user_id': 'avatar_128'}``.

``dependency_field``
    Many2many field to the same model listing the records a record depends
    on. An arrow goes from the end of each of them to the start of the record,
    red when it starts before they end.

``empty_row_labels``
    Dictionary ``{groupby_field: label}``: label of the row of the records
    without value for that field (default "None"), e.g.
    ``{'user_ids': 'Open Shifts'}``.

``progress_bar``
    Comma-separated grouped fields whose rows show a progress bar in their
    header, computed by ``_gantt_progress_bar`` on the model (see below). The
    bar is green, red when the value is above the maximum.

``display_unavailability``
    ``1`` to grey the periods returned by ``gantt_unavailability`` on the
    model (see below).

``decoration-info``, ``decoration-success``, ``decoration-warning``, ``decoration-danger``
    Python expression: the pill takes the colour of the decoration.

``decoration-muted``, ``decoration-bf``, ``decoration-it``, ``decoration-striped``
    Python expression: the pill is faded, bold, italic, or hatched (e.g.
    ``decoration-striped="state == 'draft'"`` for records not confirmed yet).

Children
--------

``<field name="..."/>``
    Fields shown in the default popover (with ``widget`` and ``options`` as
    usual) and read for the pills.

``<templates>``
    ``<t t-name="gantt-popover">`` is the body of the popover, a QWeb card
    template like calendar popovers (``<field>`` nodes, ``t-if``, ``t-out``).
    ``popover-header`` (default: the name of the record) and ``popover-footer``
    templates can be added as well; with a footer template the Edit and Delete
    buttons are replaced, unless the footer has ``replace="0"``.

Model hooks
===========

Both hooks are on every model (``base``) and do nothing by default.

Unavailable periods
-------------------

.. code-block:: python

    def gantt_unavailability(self, start_date, end_date, scale, group_bys=None, rows=None):
        """Add 'unavailabilities' to the rows: list of {'start', 'stop'} UTC datetimes."""
        for row in rows:
            if row['groupedBy'] and row['groupedBy'][-1] == 'user_id' and row['resId']:
                row['unavailabilities'] = [{'start': ..., 'stop': ...}]
            # sub-rows are in row['rows']
        return rows

Each row has ``groupedBy`` (the group by of the row and its parents),
``resId`` (its value: an id for relational fields, ``False`` for the empty
row) and ``rows`` (its sub-rows). Without group by, one row with an empty
``groupedBy`` is given, so a model can grey the closing days of the company.
``start_date`` and ``end_date`` are the visible range in UTC.

Row progress bar
----------------

.. code-block:: python

    def _gantt_progress_bar(self, field, res_ids, start, stop):
        """Return {res_id: {'value': ..., 'max': ..., 'label': optional text}}."""
        if field == 'user_id':
            return {uid: {'value': planned_hours(uid), 'max': 40} for uid in res_ids}
        return super()._gantt_progress_bar(field, res_ids, start, stop)

Server method
=============

The view loads its data with ``get_gantt_data(domain, groupby,
read_specification, order, limit, gantt_range, unavailability,
progress_bar_fields)`` on the model: the records in the visible range
(``web_read``), the groups (``formatted_read_group``, with the empty groups
of fields having a ``group_expand``), the unavailable periods and the
progress bars.

Extending the view
==================

The view is registered as ``gantt`` in the ``views`` registry. Its
``GanttController``, ``GanttModel``, ``GanttRenderer`` and
``GanttArchParser`` are exported by ``@om_web_gantt/...`` modules and can be
extended with a ``js_class``, as for any other view.

License
=======

LGPL-3. Author: Odoo Mates.
