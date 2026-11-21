===============
Report Designer
===============

This module adds a visual report designer to Odoo 20. A consultant or a power user draws a
report on its page, with the mouse, without code: the same layout prints as a PDF from the Print
menu and shows on screen from a menu.

Features
========

* A page of the chosen paper (A4, A5, Letter, Legal), portrait or landscape, with its margins,
  drawn at its real size: what the designer shows is what prints.
* Bands, from top to bottom: page header and footer (on every page), report header and footer
  (once), and record bands, repeated for each record.
* Drag the fields of the model onto a band, with their label, and the fields of related records
  (``Customer › Phone``). Add texts, lines, boxes, the company logo, the page number and the print
  date.
* Drop a list of lines (for instance the Order Lines of a sales order) on a record band: it adds
  a table of the lines under it. Drag the fields of the lines into the table, drag a column to move
  it and its edge to resize it, double click its title to rename it. A column can show its total
  under the lines; the lines can be filtered and sorted.
* Move elements with the mouse or the arrow keys, resize them by their handles; they snap to a
  grid in millimetres and to the edges of the other elements. Several elements are aligned,
  sized and spaced at once.
* Double click a text to change it. Fonts, sizes, bold, italic, underline, colors, borders,
  backgrounds and alignment for every element; formats for numbers, amounts with their currency,
  dates and images.
* Undo and redo, copy, paste and duplicate, and a preview with a real record before saving.
* Publish: the report prints from the Print menu of its records, and, when a menu is chosen,
  shows on screen for the records of a filter, with a button to download the PDF.
* The report reads the records as the user who prints it: the access rules and the company of
  the user apply.

Usage
=====

#. Report Designer > Reports > New: name the report and pick its model.
#. Open Designer, and drag the fields onto the page.
#. Publish. The report is in the Print menu of the model, and in the chosen menu.

Only the members of the group Report Designer / Designer design and publish reports.
