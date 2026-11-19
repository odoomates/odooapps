=====================
Dynamic Report Engine
=====================

The engine of the Odoo Mates dynamic reports, for Odoo 20 Community. It draws
a report on screen with its filters at the top, lines that unfold, drill-down,
saved views, and exports to PDF, Excel and CSV exactly as shown.

A report is written in Python only. The engine brings the screen, so a new
report needs no JavaScript, no QWeb and no controller.

On screen
=========

* Periods: this month, quarter, year, today, the previous ones, or a custom
  range; arrows move to the previous or next period. "As of" reports take one
  date. A report may compute the year its own way (fiscal year).
* Comparison with the previous periods or the same period of earlier years,
  for reports that support it, or with a period of custom dates.
* Amounts with decimals, in units, in thousands (K) or in millions (M), for
  reports that allow it: on screen, in the PDF and in the Excel file (the CSV
  keeps the exact amounts).
* A dropdown per record filter (journals, partners, products...), searchable,
  with several records at once.
* One-of options as their own dropdown or in the options menu; on/off options;
  numeric options.
* Column groups: one header spanning several columns (Initial Balance: Debit,
  Credit).
* Show, hide and reorder the columns; sort by a column; group by up to three
  levels, for reports that group rows.
* Lines unfold level by level, page by page ("Show more"); unfold all, fold
  all; search in the report.
* A line opens its record, the entries behind its figures, or the same line
  in another report.
* Header, first column and total stay in place while scrolling; compact or
  comfortable rows; keyboard: arrows, right and left to unfold and fold, Enter
  to open, "/" to search.
* Back from a record through the breadcrumb, the report is as it was left; the
  lines a user unfolds or folds are remembered for that user, and the report
  opens that way the next time.

Notes
=====

Write a note on any figure: hover it and click the note icon. A note belongs to
the figure, its line, its column and its period: a note on the revenue of 2026
shows on that figure wherever 2026 is shown, also as a compared period. Everyone
who can open the report reads the notes of the company; only their author
changes or deletes them. The PDF lists the notes under the table, the Excel file
puts them in cell comments.

Saved views and exports
=======================

* Save the filters, options and columns under a name, open one by default,
  share it with the other users of the company.
* PDF (company layout, A4 landscape), Excel (real numbers and dates, groups as
  Excel outline levels, column groups as a merged header, frozen header) and
  CSV, with the lines unfolded on screen or with every line.

Writing a report
================

A report is an abstract model inheriting ``om.report``, and an
``ir.actions.client`` with the tag ``om_report`` opens it.

The simple kind gives rows; the engine groups them by the dimensions the user
picks, sums the columns marked ``'aggregate': 'sum'``, sorts, searches and
pages them::

    from odoo import api, models


    class ReportSalesByCustomer(models.AbstractModel):
        _name = 'my.report.sales'
        _inherit = 'om.report'
        _description = 'Sales by Customer'

        _report_name = 'Sales by Customer'
        _report_group = 'sales_team.group_sale_salesman'
        _report_group_by = ('partner', 'product')
        _report_default_group_by = ('partner',)

        @api.model
        def _om_dimensions(self):
            return {
                'partner': {'label': self.env._("Customer"), 'model': 'res.partner', 'icon': 'person'},
                'product': {'label': self.env._("Product"), 'model': 'product.product', 'icon': 'package_2'},
            }

        @api.model
        def _om_filters(self):
            return [{'key': 'team_ids', 'label': self.env._("Sales Teams"), 'model': 'crm.team', 'icon': 'groups'}]

        @api.model
        def _om_get_columns(self, options):
            return [
                {'key': 'qty', 'label': self.env._("Quantity"), 'type': 'float', 'aggregate': 'sum'},
                {'key': 'amount', 'label': self.env._("Amount"), 'type': 'monetary', 'aggregate': 'sum'},
            ]

        @api.model
        def _om_get_rows(self, options):
            domain = [('state', '=', 'sale'), ('order_id.date_order', '>=', options['date_from']),
                      ('order_id.date_order', '<=', options['date_to'])]
            if options['team_ids']:
                domain.append(('order_id.team_id', 'in', options['team_ids']))
            return [
                {'partner_id': partner.id, 'product_id': product.id, 'qty': qty, 'amount': amount}
                for partner, product, qty, amount in self.env['sale.order.line']._read_group(
                    domain, ['order_partner_id', 'product_id'], ['product_uom_qty:sum', 'price_subtotal:sum'])
            ]

and its action::

    <record id="action_report_sales" model="ir.actions.client">
        <field name="name">Sales by Customer</field>
        <field name="tag">om_report</field>
        <field name="context">{'om_report_model': 'my.report.sales'}</field>
    </record>

What a report can declare:

* ``_report_name``, ``_report_description``, ``_report_icon``,
  ``_report_sequence``; ``_report_app`` and ``_report_section`` put it in the
  report switcher with the other reports of the same app (give
  ``om_report_app`` in the context of the action).
* ``_report_group``: the groups that may open it, comma separated.
* ``_report_date_mode``: ``'range'``, ``'as_of'`` or ``'none'``;
  ``_report_default_preset``; ``_om_date_presets`` and ``_om_year_dates`` to
  change the periods offered.
* ``_om_filters`` (records), ``_om_toggles`` (on/off), ``_om_choices`` (one of,
  ``'menu': 'bar'`` for a dropdown of its own), ``_om_numbers``: the engine adds
  them to the options with their default and checks what comes back.
* ``_om_get_columns``: ``key``, ``label``, ``type`` (char, date, datetime,
  monetary, float, int, percent), ``group``, ``aggregate``, ``visible``,
  ``optional``, ``detail_only``, ``blank_zero``, ``help``.
* ``_report_has_details`` and ``_om_detail_lines``: the lines under the last
  level of grouping.
* ``_om_line_action``: the action a line with ``drill`` opens.
* ``_report_compare`` and ``_om_compare_periods``: earlier periods to compare
  with.

A report whose lines are not a grouping of rows (a ledger, a balance sheet)
overrides ``_om_compute`` (what it computes once for the options) and
``_om_lines`` (the lines under a line, page by page), and builds its lines with
``_om_line``. The ids of the lines under a line start with the id of that line
and a ``|``.

The engine checks the options, the access to the report and the model of every
export. A report reads the data with the access rights of the user, through
the ORM, so record rules apply.

Usage
=====

The engine adds no menu: it is installed with the reports built on it, such as
Dynamic Accounting Reports.

Upgrade
=======

Version 20.0.1.1.0 adds options to the reports and changes their screen: upgrade
the module, and the reports using it, then reload the browser. From the command
line::

    odoo-bin -c <your config> -d <your database> -u om_report_engine --stop-after-init

Release Notes
=============

20.0.1.1.0
----------

* Rounding of the amounts (``_report_rounding``): with decimals, in units, in
  thousands or in millions, on screen, in the PDF and in Excel.
* Comparison with a period of custom dates.

Credits
=======

Odoo Mates, odoomates@gmail.com
