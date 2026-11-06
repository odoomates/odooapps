import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..tools import LayoutRenderer, check_layout, page_size
from ..tools.layout import PAPERS, X2MANY, _eval_domain

# records shown at once on the screen
SCREEN_LIMIT = 500
# fields the designer does not list: technical, or chatter
HIDDEN_FIELD_PREFIXES = ('message_', 'activity_', 'website_message', '__', 'rating_')
HIDDEN_FIELD_TYPES = ('properties', 'properties_definition', 'json')


class OmReportDesign(models.Model):
    """ A report drawn on a page with the designer. Publishing it makes a PDF
    report of the model (in the Print menu when asked) and, when a menu is
    chosen, a menu that shows the report on screen for the records of the
    filter. The layout is kept as JSON, see ``tools/layout.py``. """
    _name = 'om.report.design'
    _description = 'Report Design'
    _order = 'name, id'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    model = fields.Char(related='model_id.model', string='Model Name', store=True, index=True)
    domain = fields.Char(default='[]', help='The records shown when the report is run from its menu.')
    layout = fields.Json(copy=True)
    state = fields.Selection([('draft', 'Draft'), ('published', 'Published')], default='draft',
                             required=True, readonly=True, copy=False)

    paper = fields.Selection([(name, name) for name in PAPERS], default='A4', required=True)
    orientation = fields.Selection([('portrait', 'Portrait'), ('landscape', 'Landscape')],
                                   default='portrait', required=True)
    margin_top = fields.Float(default=10, help='In millimetres.')
    margin_bottom = fields.Float(default=10, help='In millimetres.')
    margin_left = fields.Float(default=10, help='In millimetres.')
    margin_right = fields.Float(default=10, help='In millimetres.')
    page_break = fields.Boolean('New Page per Record', default=True)

    print_menu = fields.Boolean('In Print Menu', default=True,
                                help='Show the report in the Print menu of the records of the model.')
    menu_parent_id = fields.Many2one('ir.ui.menu', string='Menu Under',
                                     help='Add a menu that shows the report on screen, under this menu.')
    group_ids = fields.Many2many('res.groups', string='Allowed Groups',
                                 help='Only these groups see the menu and the Print entry. Empty: every user.')

    report_action_id = fields.Many2one('ir.actions.report', readonly=True, copy=False)
    paperformat_id = fields.Many2one('report.paperformat', readonly=True, copy=False)
    view_id = fields.Many2one('ir.ui.view', readonly=True, copy=False)
    client_action_id = fields.Many2one('ir.actions.client', readonly=True, copy=False)
    menu_id = fields.Many2one('ir.ui.menu', readonly=True, copy=False)

    _check_margins = models.Constraint(
        'CHECK(margin_top >= 0 AND margin_bottom >= 0 AND margin_left >= 0 AND margin_right >= 0)',
        'Margins cannot be negative.',
    )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        designs = super().create(vals_list)
        for design in designs:
            design.layout = check_layout(design.env, design.model, design.layout or design._default_layout())
        return designs

    def write(self, vals):
        publishing = self.env.context.get('om_rd_publishing')
        changed = set(vals)
        if (vals.get('layout') or vals.get('model_id')) and not publishing:
            new_model = self.env['ir.model'].browse(vals['model_id']).model if vals.get('model_id') else None
            for design in self:
                layout = check_layout(self.env, new_model or design.model, vals.get('layout') or design.layout)
                super(OmReportDesign, design).write({'layout': layout})
            vals = {name: value for name, value in vals.items() if name != 'layout'}
        res = super().write(vals)
        published = self.filtered(lambda d: d.state == 'published')
        if published and changed & self._publish_fields() and not publishing:
            published._publish()
        return res

    def unlink(self):
        self._unpublish()
        return super().unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for design, vals in zip(self, vals_list):
            vals.setdefault('name', self.env._('%s (copy)', design.name))
        return vals_list

    @api.model
    def _publish_fields(self):
        return {'name', 'model_id', 'layout', 'paper', 'orientation', 'margin_top', 'margin_bottom',
                'margin_left', 'margin_right', 'page_break', 'print_menu', 'menu_parent_id', 'group_ids',
                'active'}

    def _default_layout(self):
        width = self._printable_width()
        return {'version': 1, 'bands': [
            {'id': 'page_header', 'kind': 'page_header', 'height': 18, 'elements': [
                {'id': 'logo', 'type': 'image', 'source': 'company', 'field': 'logo',
                 'x': 0, 'y': 1, 'w': 40, 'h': 14, 'style': {'align': 'left'}},
                {'id': 'title', 'type': 'text', 'text': self.name or '', 'x': width - 100, 'y': 3,
                 'w': 100, 'h': 9, 'style': {'font_size': 16, 'bold': True, 'align': 'right'}},
            ]},
            {'id': 'record', 'kind': 'record', 'height': 30, 'elements': []},
            {'id': 'page_footer', 'kind': 'page_footer', 'height': 8, 'elements': [
                {'id': 'page', 'type': 'page', 'text': self.env._('Page {page} / {pages}'),
                 'x': width - 40, 'y': 1, 'w': 40, 'h': 6, 'style': {'font_size': 8, 'align': 'right'}},
            ]},
        ]}

    # ------------------------------------------------------------------
    # page
    # ------------------------------------------------------------------

    def _page_size(self):
        return page_size(self.paper or 'A4', self.orientation or 'portrait')

    def _printable_width(self):
        return round(self._page_size()[0] - (self.margin_left or 0) - (self.margin_right or 0), 2)

    def _band_height(self, kind):
        return sum(b.get('height', 0) for b in (self.layout or {}).get('bands', []) if b.get('kind') == kind)

    def _paperformat_values(self):
        # the header and footer of each page sit in the top and bottom
        # margins, the body starts right after them; the spacing under the
        # header is a whole number of mm
        header = math.ceil(self._band_height('page_header'))
        footer = self._band_height('page_footer')
        return {
            'name': self.env._('Report Designer: %s', self.name),
            'format': self.paper,
            'orientation': 'Landscape' if self.orientation == 'landscape' else 'Portrait',
            'margin_top': self.margin_top + header,
            'margin_bottom': self.margin_bottom + footer,
            'margin_left': self.margin_left,
            'margin_right': self.margin_right,
            'header_spacing': header,
            'header_line': False,
            'css_margins': False,
            'disable_shrinking': True,
            'dpi': 96,
        }

    # ------------------------------------------------------------------
    # publishing
    # ------------------------------------------------------------------

    def _check_designer(self):
        if not self.env.user.has_group('om_report_designer.group_om_report_designer_manager'):
            raise AccessError(self.env._('Only report designers can change reports.'))

    def action_publish(self):
        self._check_designer()
        self._publish()
        return True

    def action_unpublish(self):
        self._check_designer()
        self._unpublish()
        return True

    def _report_name(self):
        return f'om_report_designer.design_{self.id}'

    def _publish(self):
        for design in self.sudo().with_context(om_rd_publishing=True):
            design.layout = check_layout(design.env, design.model, design.layout)
            if not design.active:
                design._unpublish()
                continue
            design._publish_report()
            design._publish_menu()
            if design.state != 'published':
                design.state = 'published'

    def _publish_report(self):
        report_name = self._report_name()
        paperformat_vals = self._paperformat_values()
        if self.paperformat_id:
            self.paperformat_id.write(paperformat_vals)
        else:
            self.paperformat_id = self.env['report.paperformat'].create(paperformat_vals)

        arch = (f'<t t-name="{report_name}"><t t-call="web.html_container">'
                '<t t-out="om_rd_html"/></t></t>')
        view_vals = {'name': report_name, 'key': report_name, 'type': 'qweb', 'arch': arch}
        if self.view_id:
            self.view_id.write(view_vals)
        else:
            self.view_id = self.env['ir.ui.view'].create(view_vals)

        report_vals = {
            'name': self.name,
            'model': self.model,
            'report_type': 'qweb-pdf',
            'report_name': report_name,
            'paperformat_id': self.paperformat_id.id,
            'binding_model_id': self.model_id.id if self.print_menu else False,
            'binding_type': 'report',
            'group_ids': [fields.Command.set(self.group_ids.ids)],
            'om_rd_design_id': self.id,
        }
        if self.report_action_id:
            self.report_action_id.write(report_vals)
        else:
            self.report_action_id = self.env['ir.actions.report'].create(report_vals)

    def _publish_menu(self):
        if not self.menu_parent_id:
            self.menu_id.unlink()
            self.client_action_id.unlink()
            return
        action_vals = {
            'name': self.name,
            'tag': 'om_report_designer_viewer',
            'params': {'design_id': self.id},
        }
        if self.client_action_id:
            self.client_action_id.write(action_vals)
        else:
            self.client_action_id = self.env['ir.actions.client'].create(action_vals)
        menu_vals = {
            'name': self.name,
            'parent_id': self.menu_parent_id.id,
            'action': f'ir.actions.client,{self.client_action_id.id}',
            'group_ids': [fields.Command.set(self.group_ids.ids)],
            'sequence': 100,
        }
        if self.menu_id:
            self.menu_id.write(menu_vals)
        else:
            self.menu_id = self.env['ir.ui.menu'].create(menu_vals)

    def _unpublish(self):
        for design in self.sudo().with_context(om_rd_publishing=True):
            design.menu_id.unlink()
            design.client_action_id.unlink()
            design.report_action_id.unlink()
            design.view_id.unlink()
            design.paperformat_id.unlink()
            if design.state != 'draft':
                design.state = 'draft'

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def _render_html(self, records, mode='html', layout=None):
        """ The report of ``records`` as HTML, read with their environment. """
        self.ensure_one()
        layout = layout if layout is not None else self.sudo().layout
        return LayoutRenderer(self.sudo(), layout or {}, records, mode).render()

    def _records(self, limit=None):
        domain = _eval_domain(self.env, self.domain or '[]')
        return self.env[self.model].search(domain, limit=limit)

    # ------------------------------------------------------------------
    # designer (client action om_report_designer)
    # ------------------------------------------------------------------

    def action_open_designer(self):
        self.ensure_one()
        self._check_designer()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_report_designer',
            'name': self.name,
            'params': {'design_id': self.id},
        }

    def _designer_settings(self):
        width, height = self._page_size()
        return {
            'id': self.id,
            'name': self.name,
            'model': self.model,
            'model_name': self.model_id.name,
            'state': self.state,
            'paper': self.paper,
            'papers': list(PAPERS),
            'orientation': self.orientation,
            'margin_top': self.margin_top,
            'margin_bottom': self.margin_bottom,
            'margin_left': self.margin_left,
            'margin_right': self.margin_right,
            'page_break': self.page_break,
            'page_width': width,
            'page_height': height,
        }

    def designer_load(self):
        self.ensure_one()
        self._check_designer()
        return {
            'settings': self._designer_settings(),
            'layout': self.layout or self._default_layout(),
            'records': self._preview_records(),
            'company_id': self.env.company.id,
        }

    def designer_save(self, layout, settings=None):
        self.ensure_one()
        self._check_designer()
        vals = {}
        for name in ('name', 'paper', 'orientation', 'margin_top', 'margin_bottom', 'margin_left',
                     'margin_right', 'page_break'):
            if settings and name in settings:
                vals[name] = settings[name]
        vals['layout'] = check_layout(self.env, self.model, layout)
        self.write(vals)
        return {'settings': self._designer_settings(), 'layout': self.layout}

    def designer_preview(self, layout, record_id=False, settings=None):
        """ HTML of the unsaved layout for one record, nothing written. """
        self.ensure_one()
        self._check_designer()
        layout = check_layout(self.env, self.model, layout)
        design = self
        if settings:
            design = self.new({name: settings[name] for name in (
                'paper', 'orientation', 'margin_left', 'margin_right', 'page_break') if name in settings},
                origin=self)
        records = self.env[self.model].browse(record_id).exists() if record_id else self.env[self.model]
        return design._render_html(records, 'html', layout=layout)

    def _preview_records(self):
        try:
            records = self._records(limit=20)
        except Exception:  # noqa: BLE001 a broken filter must not block the designer
            records = self.env[self.model].search([], limit=20)
        return [{'id': record.id, 'name': record.display_name} for record in records]

    @api.model
    def designer_fields(self, model):
        """ The fields of ``model`` the designer lists, by label. """
        self._check_designer()
        result = []
        for name, field in self.env[model].fields_get(
                attributes=['string', 'type', 'relation', 'store']).items():
            if name == 'id' or name.startswith(HIDDEN_FIELD_PREFIXES) or field['type'] in HIDDEN_FIELD_TYPES:
                continue
            result.append({
                'name': name,
                'label': field['string'] or name,
                'type': field['type'],
                'relation': field.get('relation') or False,
                'x2many': field['type'] in X2MANY,
            })
        result.sort(key=lambda f: (f['label'].lower(), f['name']))
        return result

    # ------------------------------------------------------------------
    # screen (client action om_report_designer_viewer)
    # ------------------------------------------------------------------

    def _check_viewer(self):
        if self.group_ids and not (self.group_ids & self.env.user.all_group_ids) \
                and not self.env.user.has_group('om_report_designer.group_om_report_designer_manager'):
            raise AccessError(self.env._('You are not allowed to run the report “%s”.', self.name))

    def viewer_load(self, record_ids=None):
        self.ensure_one()
        self._check_viewer()
        if record_ids:
            records = self.env[self.model].browse(record_ids).exists()
            total = len(records)
        else:
            domain = _eval_domain(self.env, self.domain or '[]')
            total = self.env[self.model].search_count(domain)
            records = self.env[self.model].search(domain, limit=SCREEN_LIMIT)
        return {
            'name': self.name,
            'html': self._render_html(records, 'html'),
            'settings': self._designer_settings(),
            'ids': records.ids,
            'count': len(records),
            'total': total,
            'can_print': bool(self.report_action_id),
            'can_design': self.env.user.has_group('om_report_designer.group_om_report_designer_manager'),
        }

    def viewer_print(self, record_ids):
        self.ensure_one()
        self._check_viewer()
        if not self.report_action_id:
            raise UserError(self.env._('Publish the report first.'))
        return self.report_action_id.report_action(record_ids, config=False)
