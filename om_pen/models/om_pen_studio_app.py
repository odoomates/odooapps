import io

from lxml import etree
from lxml.builder import E

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

from .om_pen_view import KEY_PREFIX

# features a new model can be made with, and what each one adds
FEATURES = (
    'stages', 'responsible', 'company', 'tags', 'priority', 'picture', 'lines', 'amount',
    'contact', 'dates', 'sequence', 'notes', 'chatter', 'activities', 'archiving',
)
ICON_COLORS = ('#5b2b5e', '#1f9d93', '#d9534f', '#f0ad4e', '#337ab7', '#6c757d', '#8e44ad', '#2c3e50')


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    # ------------------------------------------------------------------
    # new apps and models
    # ------------------------------------------------------------------

    @api.model
    def studio_new_app(self, values):
        """ An app in one go: a model with the chosen features, its views, an action
        and a menu of its own in the app list.
        """
        self._check_admin()
        app_name = (values.get('app_name') or '').strip()
        model_label = (values.get('model_label') or app_name).strip()
        if not app_name:
            raise UserError(_("The app needs a name."))
        model, action = self._build_model(model_label, values.get('features') or [])
        root = self.env['ir.ui.menu'].sudo().create({
            'name': app_name,
            'sequence': 100,
            'web_icon_data': self._icon(app_name, values.get('color')),
        })
        self.env['ir.ui.menu'].sudo().create({
            'name': model_label,
            'parent_id': root.id,
            'action': 'ir.actions.act_window,%s' % action.id,
            'sequence': 10,
        })
        self._configuration_menu(root, model)
        return {'model': model, 'action_id': action.id, 'menu_id': root.id}

    @api.model
    def studio_new_model(self, menu_id, values):
        """ One more model in an existing app, under its own menu. """
        self._check_admin()
        root = self.env['ir.ui.menu'].sudo().browse(int(menu_id)).exists()
        if not root:
            raise UserError(_("This app does not exist any more."))
        label = (values.get('model_label') or '').strip()
        if not label:
            raise UserError(_("The model needs a name."))
        model, action = self._build_model(label, values.get('features') or [])
        menu = self.env['ir.ui.menu'].sudo().create({
            'name': label,
            'parent_id': root.id,
            'action': 'ir.actions.act_window,%s' % action.id,
            'sequence': 50,
        })
        return {'model': model, 'action_id': action.id, 'menu_id': menu.id}

    @api.model
    def _build_model(self, label, features):
        features = [feature for feature in features if feature in FEATURES]
        has = set(features)
        fields_ = []

        def add(name, string, ttype, **extra):
            fields_.append(dict(name=name, field_description=string, ttype=ttype, **extra))

        if 'responsible' in has:
            add('x_user_id', _("Responsible"), 'many2one', relation='res.users', on_delete='set null')
        if 'company' in has:
            add('x_company_id', _("Company"), 'many2one', relation='res.company', on_delete='set null')
        if 'contact' in has:
            add('x_partner_id', _("Contact"), 'many2one', relation='res.partner', on_delete='set null')
        if 'priority' in has:
            add('x_priority', _("Priority"), 'selection', selection_ids=[
                (0, 0, {'value': value, 'name': name, 'sequence': index})
                for index, (value, name) in enumerate([('0', "Normal"), ('1', "Low"), ('2', "High"), ('3', "Very High")])])
        if 'picture' in has:
            add('x_image', _("Picture"), 'binary')
        if 'amount' in has:
            add('x_currency_id', _("Currency"), 'many2one', relation='res.currency', on_delete='set null')
            add('x_amount', _("Amount"), 'monetary', currency_field='x_currency_id')
        if 'dates' in has:
            add('x_date_start', _("Start Date"), 'date')
            add('x_date_end', _("End Date"), 'date')
        if 'sequence' in has:
            add('x_sequence', _("Sequence"), 'integer')
        if 'notes' in has:
            add('x_notes', _("Notes"), 'html')
        if 'archiving' in has:
            add('x_active', _("Active"), 'boolean')
        order = 'x_sequence, id' if 'sequence' in has else 'id desc'
        model = self._create_model(label, fields_, mail='chatter' in has or 'activities' in has,
                                   activity='activities' in has, order=order)
        Fields = self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True)
        model_id = self.env['ir.model']._get_id(model)
        if 'tags' in has:
            tag_model = self._create_model(_("%s Tag", label), [
                {'name': 'x_color', 'field_description': _("Colour"), 'ttype': 'integer'}])
            Fields.create({'name': 'x_tag_ids', 'field_description': _("Tags"), 'model': model,
                           'model_id': model_id, 'ttype': 'many2many', 'relation': tag_model,
                           'state': 'manual'})
        if 'lines' in has:
            line_model = self._create_model(_("%s Line", label), [
                {'name': 'x_sequence', 'field_description': _("Sequence"), 'ttype': 'integer'},
                {'name': 'x_quantity', 'field_description': _("Quantity"), 'ttype': 'float'},
            ], order='x_sequence, id')
            Fields.create({'name': 'x_parent_id', 'field_description': label, 'model': line_model,
                           'model_id': self.env['ir.model']._get_id(line_model), 'ttype': 'many2one',
                           'relation': model, 'on_delete': 'cascade', 'state': 'manual'})
            Fields.create({'name': 'x_line_ids', 'field_description': _("Lines"), 'model': model,
                           'model_id': model_id, 'ttype': 'one2many', 'relation': line_model,
                           'relation_field': 'x_parent_id', 'state': 'manual'})
        if 'stages' in has:
            stage_model = self._stage_model(model)
            Fields.create({'name': 'x_stage_id', 'field_description': _("Stage"), 'model': model,
                           'model_id': model_id, 'ttype': 'many2one', 'relation': stage_model,
                           'on_delete': 'restrict', 'state': 'manual', 'group_expand': True})
            first = self.env[stage_model].search([], order='x_sequence, id', limit=1)
            self.env['ir.default'].sudo().set(model, 'x_stage_id', first.id)
        defaults = self.env['ir.default'].sudo()
        if 'company' in has:
            defaults.set(model, 'x_company_id', self.env.company.id)
        if 'amount' in has:
            defaults.set(model, 'x_currency_id', self.env.company.currency_id.id)
        if 'archiving' in has:
            defaults.set(model, 'x_active', True)
        action = self._create_views_and_action(model, label, has)
        return model, action

    @api.model
    def _create_views_and_action(self, model, label, has):
        View = self.env['ir.ui.view'].sudo()
        archs = {
            'form': self._form_arch(model, has),
            'list': self._list_arch(has),
            'kanban': self._kanban_arch(has),
            'search': self._search_arch(has),
        }
        if 'dates' in has:
            archs['calendar'] = E.calendar(E.field(name='x_name'), date_start='x_date_start',
                                           date_stop='x_date_end', string=label)
        views = {}
        for view_type, arch in archs.items():
            views[view_type] = View.create({
                'name': '%s%s.%s' % (KEY_PREFIX, model, view_type),
                'key': '%s%s.%s' % (KEY_PREFIX, model, view_type),
                'model': model,
                'type': view_type,
                'arch': etree.tostring(arch, encoding='unicode', pretty_print=True),
            })
        modes = ['kanban', 'list', 'form'] if 'stages' in has else ['list', 'kanban', 'form']
        if 'dates' in has:
            modes.append('calendar')
        if 'activities' in has:
            modes.append('activity')
        action = self.env['ir.actions.act_window'].sudo().create({
            'name': label,
            'res_model': model,
            'view_mode': ','.join(modes),
            'search_view_id': views['search'].id,
            # whoever creates a record is responsible for it, unless changed
            'context': "{'default_x_user_id': uid}" if 'responsible' in has else '{}',
            'help': '<p class="o_view_nocontent_smiling_face">%s</p>' % _("Create the first %s", label),
        })
        return action

    @api.model
    def _form_arch(self, model, has):
        sheet = E.sheet()
        if 'picture' in has:
            sheet.append(E.field(name='x_image', widget='image', **{'class': 'oe_avatar'}))
        title = E.div(E.h1(E.field(name='x_name', placeholder=_("Name"))), **{'class': 'oe_title'})
        if 'priority' in has:
            title.insert(0, E.field(name='x_priority', widget='priority'))
        sheet.append(title)
        left, right = E.group(name='x_pen_left'), E.group(name='x_pen_right')
        for feature, name, column, extra in (
                ('contact', 'x_partner_id', left, {}),
                ('responsible', 'x_user_id', left, {'widget': 'many2one_avatar_user'}),
                ('tags', 'x_tag_ids', left, {'widget': 'many2many_tags', 'options': "{'color_field': 'x_color'}"}),
                ('dates', 'x_date_start', right, {}),
                ('dates', 'x_date_end', right, {}),
                ('amount', 'x_amount', right, {}),
                ('amount', 'x_currency_id', right, {'invisible': '1'}),
                ('company', 'x_company_id', right, {'groups': 'base.group_multi_company'}),
                ('archiving', 'x_active', right, {'invisible': '1'}),
                ('sequence', 'x_sequence', right, {'invisible': '1'})):
            if feature in has:
                column.append(E.field(name=name, **extra))
        sheet.append(E.group(left, right, name='x_pen_main'))
        pages = []
        if 'lines' in has:
            lines = E.field(E.list(E.field(name='x_sequence', widget='handle'), E.field(name='x_name'),
                                   E.field(name='x_quantity'), editable='bottom'), name='x_line_ids')
            pages.append(E.page(lines, string=_("Lines"), name='x_pen_lines'))
        if 'notes' in has:
            pages.append(E.page(E.field(name='x_notes'), string=_("Notes"), name='x_pen_notes'))
        if pages:
            sheet.append(E.notebook(*pages))
        form = E.form()
        if 'stages' in has:
            form.append(E.header(E.field(name='x_stage_id', widget='statusbar', options="{'clickable': '1'}")))
        if 'archiving' in has:
            sheet.insert(0, E.widget(name='web_ribbon', title=_("Archived"), bg_color='text-bg-danger',
                                     invisible='x_active'))
        form.append(sheet)
        if 'chatter' in has or 'activities' in has:
            form.append(E.chatter())
        return form

    @api.model
    def _list_arch(self, has):
        tree = E.list()
        if 'sequence' in has:
            tree.append(E.field(name='x_sequence', widget='handle'))
        tree.append(E.field(name='x_name'))
        for feature, name, extra in (
                ('contact', 'x_partner_id', {}),
                ('responsible', 'x_user_id', {'widget': 'many2one_avatar_user'}),
                ('dates', 'x_date_start', {}),
                ('amount', 'x_amount', {'sum': _("Total")}),
                ('amount', 'x_currency_id', {'column_invisible': '1'}),
                ('priority', 'x_priority', {'widget': 'priority', 'optional': 'show'}),
                ('tags', 'x_tag_ids', {'widget': 'many2many_tags', 'optional': 'show'}),
                ('stages', 'x_stage_id', {}),
                ('company', 'x_company_id', {'groups': 'base.group_multi_company', 'optional': 'show'})):
            if feature in has:
                tree.append(E.field(name=name, **extra))
        return tree

    @api.model
    def _kanban_arch(self, has):
        card = E.t(E.field(name='x_name', **{'class': 'fw-bold fs-5'}), **{'t-name': 'card'})
        if 'contact' in has:
            card.append(E.field(name='x_partner_id'))
        if 'tags' in has:
            card.append(E.field(name='x_tag_ids', widget='many2many_tags', options="{'color_field': 'x_color'}"))
        if 'amount' in has:
            card.append(E.field(name='x_amount', widget='monetary'))
        footer = E.footer()
        if 'priority' in has:
            footer.append(E.field(name='x_priority', widget='priority'))
        if 'responsible' in has:
            footer.append(E.field(name='x_user_id', widget='many2one_avatar_user', **{'class': 'ms-auto'}))
        if len(footer):
            card.append(footer)
        if 'picture' in has:
            card.insert(0, E.aside(E.field(name='x_image', widget='image')))
        kanban = E.kanban(E.templates(card))
        if 'amount' in has:
            kanban.insert(0, E.field(name='x_currency_id'))
        if 'stages' in has:
            kanban.set('default_group_by', 'x_stage_id')
        return kanban

    @api.model
    def _search_arch(self, has):
        search = E.search(E.field(name='x_name'))
        if 'contact' in has:
            search.append(E.field(name='x_partner_id'))
        if 'responsible' in has:
            search.append(E.field(name='x_user_id'))
            search.append(E.filter(name='x_pen_mine', string=_("Mine"), domain="[('x_user_id', '=', uid)]"))
        if 'archiving' in has:
            search.append(E.separator())
            search.append(E.filter(name='x_pen_archived', string=_("Archived"), domain="[('x_active', '=', False)]"))
        groups = []
        if 'stages' in has:
            groups.append(E.filter(name='x_pen_by_stage', string=_("Stage"), context="{'group_by': 'x_stage_id'}"))
        if 'responsible' in has:
            groups.append(E.filter(name='x_pen_by_user', string=_("Responsible"), context="{'group_by': 'x_user_id'}"))
        if groups:
            search.append(E.group(*groups))
        return search

    @api.model
    def _configuration_menu(self, root, model):
        """ A Configuration menu for the stages and tags the app was made with. """
        targets = []
        for field_name, label in (('x_stage_id', _("Stages")), ('x_tag_ids', _("Tags"))):
            field = self.env[model]._fields.get(field_name)
            if field:
                targets.append((field.comodel_name, label))
        if not targets:
            return
        config = self.env['ir.ui.menu'].sudo().create({'name': _("Configuration"), 'parent_id': root.id, 'sequence': 90})
        for comodel, label in targets:
            action = self.env['ir.actions.act_window'].sudo().create({
                'name': label, 'res_model': comodel, 'view_mode': 'list,form'})
            self.env['ir.ui.menu'].sudo().create({
                'name': label, 'parent_id': config.id, 'action': 'ir.actions.act_window,%s' % action.id})

    @api.model
    def _icon(self, name, color=None):
        """ A square icon with the first letter of the app, in its colour. """
        from PIL import Image, ImageDraw, ImageFont
        color = color if color in ICON_COLORS else ICON_COLORS[0]
        size = 256
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=48, fill=color)
        letter = (name.strip()[:1] or 'A').upper()
        try:
            font = ImageFont.truetype('DejaVuSans-Bold.ttf', 150)
        except OSError:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), letter, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]),
                  letter, fill='white', font=font)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return BinaryBytes(buffer.getvalue())

    # ------------------------------------------------------------------
    # menus
    # ------------------------------------------------------------------

    @api.model
    def studio_apps(self):
        """ The top level menus, to pick the app whose menus are edited. """
        self._check()
        roots = self.env['ir.ui.menu'].with_context(active_test=False).search([('parent_id', '=', False)])
        return [{'id': menu.id, 'name': menu.name, 'active': menu.active} for menu in roots]

    @api.model
    def studio_app_of_action(self, action_id):
        """ The app a window action belongs to, through the menu that opens it. """
        self._check()
        menu = self.env['ir.ui.menu'].search([('action', '=', 'ir.actions.act_window,%s' % int(action_id or 0))], limit=1)
        while menu.parent_id:
            menu = menu.parent_id
        return menu.id or False

    @api.model
    def studio_menus(self, root_id):
        self._check()
        Menu = self.env['ir.ui.menu'].with_context(active_test=False)
        root = Menu.browse(int(root_id)).exists()
        if not root:
            raise UserError(_("This app does not exist any more."))
        xmlids = Menu.search([('id', 'child_of', root.id)]).get_external_id()

        def describe(menu, depth):
            children = Menu.search([('parent_id', '=', menu.id)], order='sequence, id')
            return {
                'id': menu.id,
                'name': menu.name,
                'sequence': menu.sequence,
                'active': menu.active,
                'depth': depth,
                'action': menu.action and menu.action.display_name or '',
                'model': menu.action.res_model if menu.action and menu.action._name == 'ir.actions.act_window' else False,
                'action_id': menu.action.id if menu.action and menu.action._name == 'ir.actions.act_window' else False,
                'standard': bool(xmlids.get(menu.id)) and not xmlids[menu.id].startswith('__'),
                'groups': menu.group_ids.mapped('display_name') if 'group_ids' in menu._fields else [],
                'children': [describe(child, depth + 1) for child in children],
            }
        return describe(root, 0)

    @api.model
    def studio_menu_update(self, menu_id, values):
        """ Rename, show or hide a menu, or move it among its siblings. """
        self._check_admin()
        menu = self.env['ir.ui.menu'].sudo().with_context(active_test=False).browse(int(menu_id)).exists()
        if not menu:
            raise UserError(_("This menu does not exist any more."))
        vals = {}
        if values.get('name'):
            vals['name'] = values['name']
        if 'active' in values:
            vals['active'] = bool(values['active'])
        if vals:
            menu.write(vals)
        if values.get('move') in ('up', 'down'):
            siblings = menu.search([('parent_id', '=', menu.parent_id.id)], order='sequence, id')
            siblings = list(siblings)
            index = siblings.index(menu)
            other = index - 1 if values['move'] == 'up' else index + 1
            if 0 <= other < len(siblings):
                siblings[index], siblings[other] = siblings[other], siblings[index]
                for position, sibling in enumerate(siblings):
                    sibling.sequence = (position + 1) * 10
        return True

    @api.model
    def studio_menu_create(self, parent_id, values):
        """ A menu under `parent_id`: a submenu, an existing action, or a new model. """
        self._check_admin()
        parent = self.env['ir.ui.menu'].sudo().browse(int(parent_id)).exists()
        if not parent:
            raise UserError(_("Pick where the menu goes."))
        name = (values.get('name') or '').strip()
        if not name:
            raise UserError(_("The menu needs a name."))
        vals = {'name': name, 'parent_id': parent.id, 'sequence': 100}
        if values.get('kind') == 'model':
            _model, action = self._build_model(name, values.get('features') or [])
            vals['action'] = 'ir.actions.act_window,%s' % action.id
        elif values.get('kind') == 'action' and values.get('action_id'):
            action = self.env['ir.actions.act_window'].browse(int(values['action_id'])).exists()
            if not action:
                raise UserError(_("Pick the action the menu opens."))
            vals['action'] = 'ir.actions.act_window,%s' % action.id
        return self.env['ir.ui.menu'].sudo().create(vals).id

    @api.model
    def studio_menu_delete(self, menu_id):
        """ Delete a menu made here; a menu of a module can only be hidden. """
        self._check_admin()
        menu = self.env['ir.ui.menu'].sudo().with_context(active_test=False).browse(int(menu_id)).exists()
        if not menu:
            return True
        xmlid = menu.get_external_id().get(menu.id)
        if xmlid and not xmlid.startswith('__'):
            raise UserError(_("This menu comes from a module: hide it instead."))
        menu.with_context(active_test=False).search([('id', 'child_of', menu.id)]).unlink()
        return True

    @api.model
    def studio_window_actions(self):
        self._check()
        return [{'id': action.id, 'name': '%s (%s)' % (action.name, action.res_model)}
                for action in self.env['ir.actions.act_window'].search([], order='name', limit=500)]
