""" PDF reports built from blocks.

A report is a list of blocks (a title, a text with fields, a table of lines...). The
QWeb template is generated from them here, never typed by the user: their text goes
into the template as text, and their fields are checked against the model.
"""
import re

from markupsafe import Markup
from lxml import etree
from lxml.builder import E

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .om_pen_view import KEY_PREFIX

BLOCK_KINDS = ('title', 'text', 'field', 'fields', 'address', 'table', 'image', 'signature',
               'qrcode', 'barcode', 'spacer', 'page_break', 'columns_end')
PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}')
ALIGNS = ('start', 'center', 'end')


class OmPenReport(models.Model):
    _name = 'om.pen.report'
    _description = "Report Made In Pen Studio"
    _order = 'id desc'

    name = fields.Char(required=True)
    model = fields.Char(required=True, index=True)
    blocks = fields.Json(default=list)
    layout = fields.Selection([('external', "With the company header and footer"),
                               ('basic', "Blank page")], default='external', required=True)
    report_id = fields.Many2one('ir.actions.report', string="Report", ondelete='cascade', readonly=True)
    view_id = fields.Many2one('ir.ui.view', string="Template", ondelete='set null', readonly=True)
    # blocks added to a report of a module instead of a report of their own
    inherit_report_id = fields.Many2one('ir.actions.report', string="Added To", ondelete='cascade')
    position = fields.Selection([('top', "Above the report"), ('bottom', "Below the report")], default='bottom')

    # ------------------------------------------------------------------
    # generation
    # ------------------------------------------------------------------

    def _template_key(self):
        self.ensure_one()
        return '%sreport_%s' % (KEY_PREFIX, self.id)

    def _check_path(self, path, model=None):
        """ Raise unless `path` is a dotted path of fields of the model. """
        current = self.env[model or self.model]
        for name in path.split('.'):
            field = current._fields.get(name)
            if not field:
                raise UserError(_("%(model)s has no field %(field)s.", model=current._name, field=name))
            if field.relational:
                current = self.env[field.comodel_name]
        return path

    def _text_nodes(self, parent, text, var):
        """ Put `text` in `parent`, turning {{ field.path }} into the field's value. """
        position = 0
        last = None
        for match in PLACEHOLDER_RE.finditer(text or ''):
            chunk = text[position:match.start()]
            self._append_text(parent, last, chunk)
            path = self._check_path(match.group(1))
            last = etree.SubElement(parent, 'span', {'t-field': '%s.%s' % (var, path)})
            position = match.end()
        self._append_text(parent, last, (text or '')[position:])

    @staticmethod
    def _append_text(parent, last, chunk):
        if not chunk:
            return
        if last is None:
            parent.text = (parent.text or '') + chunk
        else:
            last.tail = (last.tail or '') + chunk

    def _block_node(self, index, block, var):
        """ The QWeb of one block. Every block is wrapped in a div carrying its index,
        so a click in the preview selects it in the designer.
        """
        kind = block.get('kind')
        if kind not in BLOCK_KINDS:
            raise UserError(_("Unknown block: %s", kind))
        align = block.get('align') if block.get('align') in ALIGNS else 'start'
        wrapper = E.div({'class': 'o_pen_block mb-3 text-%s' % align, 'data-pen-block': str(index)})
        if block.get('condition'):
            path = self._check_path(block['condition'])
            wrapper.set('t-if', '%s.%s' % (var, path))
        if kind == 'title':
            node = etree.SubElement(wrapper, 'h%s' % (block.get('level') if block.get('level') in (1, 2, 3) else 2))
            self._text_nodes(node, block.get('text') or _("Title"), var)
        elif kind == 'text':
            for line in (block.get('text') or '').split('\n'):
                paragraph = etree.SubElement(wrapper, 'p', {'class': 'mb-1'})
                self._text_nodes(paragraph, line, var)
        elif kind == 'field':
            path = self._check_path(block.get('field') or '')
            if block.get('label'):
                etree.SubElement(wrapper, 'strong').text = '%s: ' % block['label']
            etree.SubElement(wrapper, 'span', {'t-field': '%s.%s' % (var, path)})
        elif kind == 'fields':
            table = etree.SubElement(wrapper, 'table', {'class': 'table table-sm table-borderless'})
            items = block.get('fields') or []
            for start in range(0, len(items), 2):
                row = etree.SubElement(table, 'tr')
                for item in items[start:start + 2]:
                    path = self._check_path(item.get('field') or '')
                    etree.SubElement(row, 'td', {'class': 'fw-bold', 'style': 'width: 20%'}).text = \
                        item.get('label') or self._field_label(path)
                    etree.SubElement(etree.SubElement(row, 'td'), 'span', {'t-field': '%s.%s' % (var, path)})
        elif kind == 'address':
            path = self._check_path(block.get('field') or '')
            etree.SubElement(wrapper, 'div', {
                't-field': '%s.%s' % (var, path),
                't-options': "{'widget': 'contact', 'fields': ['address', 'name', 'phone', 'email'], 'no_marker': True}",
            })
        elif kind == 'table':
            wrapper.append(self._table_node(block, var))
        elif kind in ('image', 'signature'):
            path = self._check_path(block.get('field') or '')
            if block.get('label'):
                etree.SubElement(wrapper, 'div', {'class': 'fw-bold'}).text = block['label']
            etree.SubElement(wrapper, 'img', {
                't-if': '%s.%s' % (var, path),
                't-att-src': 'image_data_uri(%s.%s)' % (var, path),
                'style': 'max-height: %spx; max-width: 100%%;' % int(block.get('height') or 120),
            })
        elif kind in ('qrcode', 'barcode'):
            # an image fetched from the barcode route: drawn when printed, so a missing
            # barcode library on the server shows as a missing image, not a broken report
            path = self._check_path(block.get('field') or '')
            symbology, width, height = ('QR', 150, 150) if kind == 'qrcode' else ('Code128', 600, 100)
            etree.SubElement(wrapper, 'img', {
                't-if': '%s.%s' % (var, path),
                't-att-src': "'/report/barcode/%s/%%s?width=%s&height=%s' %% quote_plus(str(%s.%s))" % (
                    symbology, width, height, var, path),
                'style': 'max-width: 100%%; height: %spx;' % (height if kind == 'barcode' else width),
            })
        elif kind == 'spacer':
            wrapper.set('style', 'height: %spx' % int(block.get('height') or 24))
        elif kind == 'page_break':
            wrapper.set('style', 'page-break-after: always;')
        return wrapper

    def _field_label(self, path):
        current = self.env[self.model]
        field = None
        for name in path.split('.'):
            field = current._fields[name]
            if field.relational:
                current = self.env[field.comodel_name]
        return field._description_string(self.env) if field else path

    def _table_node(self, block, var):
        """ A table of the lines of an x2many, with an optional total row. """
        lines = block.get('lines') or ''
        field = self.env[self.model]._fields.get(lines)
        if not field or field.type not in ('one2many', 'many2many'):
            raise UserError(_("Pick the lines the table shows."))
        comodel = field.comodel_name
        columns = block.get('columns') or []
        if not columns:
            raise UserError(_("A table needs at least one column."))
        head = E.tr()
        body = E.tr({'t-foreach': '%s.%s' % (var, lines), 't-as': 'line'})
        totals = []
        for column in columns:
            path = self._check_path(column.get('field') or '', comodel)
            sub = self.env[comodel]._fields[path.split('.')[0]]
            numeric = sub.type in ('integer', 'float', 'monetary')
            cell_class = 'text-end' if numeric else ''
            head.append(E.th(column.get('label') or sub._description_string(self.env), {'class': cell_class}))
            body.append(E.td(E.span({'t-field': 'line.%s' % path}), {'class': cell_class}))
            totals.append(path if numeric and column.get('total') else None)
        if block.get('highlight'):
            path = self._check_path(block['highlight'], comodel)
            body.set('t-att-class', "'fw-bold' if line.%s else ''" % path)
        table = E.table({'class': 'table table-sm o_main_table'}, E.thead(head), E.tbody(body))
        if any(totals):
            row = E.tr({'class': 'fw-bold border-top'})
            for index, path in enumerate(totals):
                if path:
                    row.append(E.td(E.span({'t-out': "sum(%s.%s.mapped('%s'))" % (var, lines, path),
                                            't-options': "{'widget': 'float', 'precision': 2}"}),
                                    {'class': 'text-end'}))
                else:
                    row.append(E.td(_("Total") if index == 0 else ''))
            table.append(E.tfoot(row))
        return table

    def _blocks_nodes(self, var):
        self.ensure_one()
        return [self._block_node(index, block, var) for index, block in enumerate(self.blocks or [])]

    def _arch(self):
        """ The QWeb template of a report of its own. """
        self.ensure_one()
        page = E.div({'class': 'page o_pen_report'}, *self._blocks_nodes('o'))
        layout = 'web.external_layout' if self.layout == 'external' else 'web.basic_layout'
        template = E.t(
            E.t(E.t(E.t(page, {'t-call': layout}), {'t-foreach': 'docs', 't-as': 'o'}),
                {'t-call': 'web.html_container'}),
            {'t-name': self._template_key()})
        return etree.tostring(template, encoding='unicode', pretty_print=True)

    def _extension_target(self):
        """ The template holding the page of a module's report, and its record variable.

        A report template usually calls others before reaching the page (the report,
        then a raw version, then the document): follow the calls until a template has
        the page in it.
        """
        self.ensure_one()
        report = self.inherit_report_id
        View = self.env['ir.ui.view'].sudo()
        key, var = report.report_name, 'doc'
        for _depth in range(6):
            view = View.search([('key', '=', key), ('type', '=', 'qweb')], limit=1)
            if not view:
                break
            primary = view
            while primary.mode != 'primary' and primary.inherit_id:
                primary = primary.inherit_id
            arch = primary._get_combined_arch()
            loop = arch.xpath("//t[@t-foreach='docs']")
            if loop:
                var = loop[0].get('t-as') or var
            if arch.xpath("//div[hasclass('page')]"):
                return primary, var
            calls = [node.get('t-call') for node in arch.xpath('//t[@t-call]')
                     if not node.get('t-call').startswith('web.')]
            if not calls:
                break
            key = calls[0]
        raise UserError(_("Blocks cannot be added to %s: its layout is not supported.", report.name))

    def _extension_arch(self, var):
        self.ensure_one()
        nodes = self._blocks_nodes(var)
        if self.position == 'top':
            spec = E.xpath(*nodes, expr="//div[hasclass('page')]/*[1]", position='before')
        else:
            spec = E.xpath(*nodes, expr="//div[hasclass('page')]", position='inside')
        return etree.tostring(E.data(spec), encoding='unicode', pretty_print=True)

    def _apply(self, values=None):
        """ Write the template and the report action from the blocks. """
        self.ensure_one()
        values = values or {}
        View = self.env['ir.ui.view'].sudo()
        if self.inherit_report_id:
            target, var = self._extension_target()
            vals = {'arch': self._extension_arch(var)}
            if self.view_id:
                self.view_id.write(vals)
            else:
                self.view_id = View.create({
                    **vals,
                    'name': self._template_key(),
                    'type': 'qweb',
                    'inherit_id': target.id,
                    'priority': 99,
                })
            return
        vals = {'arch': self._arch()}
        if self.view_id:
            self.view_id.write(vals)
        else:
            self.view_id = View.create({**vals, 'name': self._template_key(), 'key': self._template_key(), 'type': 'qweb'})
            self.env['ir.model.data'].sudo().create({
                'module': '__custom__', 'name': 'om_pen_report_%s' % self.id,
                'model': 'ir.ui.view', 'res_id': self.view_id.id, 'noupdate': True})
        report_vals = {
            'name': self.name,
            'model': self.model,
            'report_type': 'qweb-pdf',
            'report_name': self._template_key(),
        }
        for key in ('paperformat_id', 'print_report_name'):
            if key in values:
                report_vals[key] = values[key] or False
        if 'group_ids' in values:
            report_vals['group_ids'] = [(6, 0, values['group_ids'] or [])]
        Report = self.env['ir.actions.report'].sudo()
        if self.report_id:
            self.report_id.write(report_vals)
        else:
            self.report_id = Report.create(report_vals)
        if 'print_menu' in values:
            if values['print_menu']:
                self.report_id.create_action()
            else:
                self.report_id.unlink_action()


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    @api.model
    def studio_reports(self, model):
        """ The reports of the model: the ones made here and the ones of modules. """
        self._check()
        own = self.env['om.pen.report'].search([('model', '=', model)])
        made = own.report_id
        standard = self.env['ir.actions.report'].search([('model', '=', model), ('id', 'not in', made.ids)])
        return {
            'own': [{'id': report.id, 'name': report.name, 'added_to': report.inherit_report_id.name or False,
                     'position': report.position} for report in own],
            'standard': [{'id': report.id, 'name': report.name} for report in standard],
            'paperformats': [{'id': paper.id, 'name': paper.name} for paper in self.env['report.paperformat'].search([])],
        }

    @api.model
    def studio_report_create(self, model, values):
        self._check_admin()
        values = dict(values)
        inherit = values.get('inherit_report_id')
        name = values.get('name') or _("New Report")
        blocks = values.get('blocks') or self._starter_blocks(model, bool(inherit))
        report = self.env['om.pen.report'].create({
            'name': name,
            'model': model,
            'blocks': blocks,
            'inherit_report_id': inherit or False,
            'position': values.get('position') or 'bottom',
        })
        report._apply({'print_menu': True} if not inherit else {})
        return self.studio_report_load(report.id)

    @api.model
    def _starter_blocks(self, model, extension):
        """ Something to start from: the name of the record and a few of its fields. """
        if extension:
            return [{'kind': 'text', 'text': _("Added by Pen Studio")}]
        Model = self.env[model]
        blocks = [{'kind': 'title', 'text': '{{ %s }}' % (Model._rec_name or 'display_name'), 'level': 2}]
        # start from what the form shows: those are the fields people care about
        form = etree.fromstring(Model.get_view(view_type='form')['arch'])
        shown = [node for node in form.xpath('//sheet//field[not(ancestor::field)][ancestor::group or ancestor::page]')
                 if node.get('name') in Model._fields and node.get('invisible') in (None, '0', 'False')
                 and not node.xpath('ancestor::div[@name="button_box"]')]
        picked, lines = [], None
        for node in shown:
            name = node.get('name')
            field = Model._fields[name]
            if field.type == 'one2many' and not lines and len(node):
                lines = (name, node)
            elif field.type not in ('one2many', 'many2many', 'binary', 'html', 'properties', 'json') \
                    and name != Model._rec_name and name not in picked and len(picked) < 6:
                picked.append(name)
        if picked:
            blocks.append({'kind': 'fields', 'fields': [{'field': name} for name in picked]})
        if lines:
            name, node = lines
            comodel = self.env[Model._fields[name].comodel_name]
            columns = []
            for sub in node.xpath("./list/field[not(@widget='handle')][not(@optional='hide')]"):
                sub_name = sub.get('name')
                sub_field = comodel._fields.get(sub_name)
                if sub_field and sub.get('column_invisible') not in ('1', 'True') \
                        and sub_field.type not in ('one2many', 'many2many', 'binary', 'html') and len(columns) < 5:
                    columns.append(sub_name)
            if len(columns) < 2:
                # some lists draw their lines with a widget of their own and hide the
                # columns: fall back on the usual ones
                usual = ('product_id', 'name', 'product_uom_qty', 'quantity', 'price_unit', 'price_subtotal')
                columns = [c for c in usual if c in comodel._fields][:5] or columns
            if columns:
                numeric = ('integer', 'float', 'monetary')
                blocks.append({'kind': 'table', 'lines': name, 'columns': [
                    {'field': c, 'total': c in ('price_subtotal', 'price_total')
                     and comodel._fields[c].type in numeric} for c in columns]})
        blocks.append({'kind': 'spacer', 'height': 40})
        blocks.append({'kind': 'text', 'text': _("Signature:")})
        return blocks

    @api.model
    def studio_report_load(self, report_id):
        self._check()
        report = self.env['om.pen.report'].browse(int(report_id)).exists()
        if not report:
            raise UserError(_("This report does not exist any more."))
        action = report.report_id
        return {
            'id': report.id,
            'name': report.name,
            'model': report.model,
            'blocks': report.blocks or [],
            'layout': report.layout,
            'added_to': report.inherit_report_id.name or False,
            'position': report.position,
            'paperformat_id': action.paperformat_id.id or False,
            'print_report_name': action.print_report_name or '',
            'print_menu': bool(action.binding_model_id),
            'group_ids': action.group_ids.ids,
            'report_name': (report.inherit_report_id or action).report_name or False,
            'paperformats': [{'id': paper.id, 'name': paper.name}
                             for paper in self.env['report.paperformat'].search([])],
        }

    @api.model
    def studio_report_save(self, report_id, values):
        """ Save the blocks and the settings; the template is generated again. """
        self._check_admin()
        report = self.env['om.pen.report'].browse(int(report_id)).exists()
        if not report:
            raise UserError(_("This report does not exist any more."))
        vals = {key: values[key] for key in ('name', 'blocks', 'layout', 'position') if key in values}
        with self.env.cr.savepoint():
            report.write(vals)
            report._apply(values)
            # render once, so a block that breaks the template is refused now
            record = self.env[report.model].search([], limit=1)
            if record:
                self._render_report(report, record.id)
        return self.studio_report_load(report.id)

    @api.model
    def studio_report_delete(self, report_id):
        self._check_admin()
        report = self.env['om.pen.report'].browse(int(report_id)).exists()
        report.view_id.unlink()
        report.report_id.unlink()
        report.unlink()
        return True

    @api.model
    def studio_report_preview(self, report_id, res_id=False):
        """ The report as HTML, on a record of the model. """
        self._check()
        report = self.env['om.pen.report'].browse(int(report_id)).exists()
        if not report:
            raise UserError(_("This report does not exist any more."))
        record = self.env[report.model].browse(int(res_id or 0)).exists() or \
            self.env[report.model].search([], order='id desc', limit=1)
        if not record:
            return {'html': '<p style="font-family: sans-serif; color: #777; padding: 2rem">%s</p>' % _(
                "Create a record first: the preview shows the report of a record."), 'res_id': False}
        try:
            html = self._render_report(report, record.id)
        except Exception as error:  # noqa: BLE001 - shown in the designer instead of the preview
            return {'html': Markup('<pre style="color: #b42318; padding: 1rem; white-space: pre-wrap">%s</pre>') % str(error),
                    'res_id': record.id}
        return {'html': html, 'res_id': record.id, 'record_name': record.display_name}

    @api.model
    def _render_report(self, report, res_id):
        action = report.inherit_report_id or report.report_id
        html, _type = self.env['ir.actions.report']._render_qweb_html(action.report_name, [res_id])
        return html.decode() if isinstance(html, bytes) else html

    @api.model
    def studio_report_records(self, model):
        self._check()
        return [{'id': record.id, 'name': record.display_name}
                for record in self.env[model].search([], order='id desc', limit=30)]
