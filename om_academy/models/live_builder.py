# Build it live: what installing the learner's module would create, created
# in the database instead. Models and fields are custom ones (x_ names, as
# Odoo requires), methods become server actions, and the views, actions,
# menus and access rights are read from the module's own XML and CSV files.
# Every change is logged per step, so that a step can be undone exactly.
import ast
import re
from contextlib import nullcontext

from lxml import etree

from odoo.exceptions import UserError
from odoo.modules.module import get_module_path
from odoo.tools import mute_logger
from odoo.tools.binary import BinaryBytes
from odoo.tools.translate import LazyTranslate

from .course_files import course_models, csv_accesses, files_at, models_at, xml_records

_lt = LazyTranslate(__name__)

# a step replacing a field, e.g. the text Author by a link Author, adds the new field before the views stop using the
# old one: for a moment both have the same label, which Odoo logs as a warning that means nothing here
SAME_LABEL_LOGGER = 'odoo.addons.base.models.ir_model'

# the external ids of the groups built live, for the groups="..." of views
LIVE_MODULE = 'om_academy_live'
MODIFIER_ATTRIBUTES = ('invisible', 'readonly', 'required', 'column_invisible', 'domain', 'context',
                       'filter_domain', 'expr', 'default_group_by', 'highlight_color', 'default_order')


def live_model(model):
    return 'x_' + model.replace('.', '_')


def live_field(name):
    return name if name.startswith('x_') else 'x_' + name


class LiveBuilder:
    """ Builds the steps of a course for one progress record. ``progress.live_map``
    gives the record created for each key ('model:library.book',
    'field:library.book.name', 'method:library.book.action_borrow', or the
    xmlid of a record of the module's files); ``progress.live_log`` lists, per
    step, what was done, newest last. """

    def __init__(self, progress, course):
        self.progress = progress
        self.env = progress.env
        self.course = course
        self.created_models = course_models(course)
        self.map = dict(progress.live_map or {})
        self.log = {key: list(entries) for key, entries in (progress.live_log or {}).items()}

    def save(self):
        self.progress.write({'live_map': self.map, 'live_log': self.log})

    def model_name(self, model):
        """ The name of a model live: x_ for the models the course creates, the
        same for the models of Odoo it extends. """
        return live_model(model) if model in self.created_models else model

    def ir_model(self, model):
        return self.record('model:' + model) or self.env['ir.model']._get(model)

    def record(self, key):
        entry = self.map.get(key)
        if not entry:
            return None
        return self.env[entry[0]].sudo().browse(entry[1]).exists() or None

    def _created(self, step_key, key, record):
        self.map[key] = [record._name, record.id]
        self.log.setdefault(step_key, []).append({'do': 'create', 'model': record._name, 'id': record.id, 'key': key})
        self._own(key, record)

    #
    # the app built live is a module of the database, as Odoo imports them:
    # in Apps, installed, and every record it built belongs to it
    #

    def _data_name(self, key):
        """ The external id, in the learner's module, of what a key of the map names. """
        kind, _sep, name = key.partition(':')
        if not _sep:
            return key  # an id of the module's files
        if kind == 'model':
            return 'model_' + self.model_name(name).replace('.', '_')
        if kind == 'field':
            model, field = name.rsplit('.', 1)
            return 'field_%s__%s' % (self.model_name(model).replace('.', '_'), live_field(field))
        if kind == 'method':
            return 'action_server_' + name.replace('.', '_')
        if kind == 'icon':
            return 'attachment_icon'
        return None  # defaults and the ids of groups follow their records

    def _own(self, key, record):
        name = self._data_name(key)
        if not name or record._name in ('ir.model.data', 'ir.module.module'):
            return
        Data = self.env['ir.model.data'].sudo()
        module = self.course['module']
        Data.search([('module', '=', module), ('name', '=', name)]).unlink()
        Data.create({'module': module, 'name': name, 'model': record._name, 'res_id': record.id, 'noupdate': True})

    def module(self):
        return self.env['ir.module.module'].sudo().search([('name', '=', self.course['module'])], limit=1)

    def _sync_module(self, step_key, index):
        """ The module of the app built live, as its manifest says after the step:
        registered the first time, kept up to date after. """
        manifest = ast.literal_eval(files_at(self.course, index).get('__manifest__.py') or '{}')
        module_name = self.course['module']
        values = {
            'shortdesc': manifest.get('name') or module_name,
            'summary': manifest.get('summary') or False,
            'author': manifest.get('author') or False,
            'license': manifest.get('license') or 'LGPL-3',
            'application': bool(manifest.get('application')),
            'latest_version': manifest.get('version') or '1.0',
            'icon': '/%s/static/description/icon.png' % module_name,
            'description': 'Built live with the Odoo Mates Academy.',
        }
        module = self.module()
        if not self.record('module:' + module_name):
            path = get_module_path(module_name, display_warning=False)
            if path:
                # Odoo would load the module of the folder over the app built live
                raise UserError(str(_lt(
                    "Your module %(module)s is in your addons folder (%(path)s): Odoo would mix it "
                    "with an app built live. Go on in Code it, or move the folder out of the "
                    "addons path and restart Odoo.")) % {'module': module_name, 'path': path})
        if module and not self.record('module:' + module_name):
            if module.state == 'installed':
                self._already_built('module:' + module_name, module_name)
            module.unlink()  # known to Odoo, not installed: the files of a learner
            module = None
        if module:
            module.write(values)
        else:
            module = self.env['ir.module.module'].sudo().create(
                dict(values, name=module_name, state='installed', imported=True))
            self._created(step_key, 'module:' + module_name, module)
            # what was built before the module existed belongs to it too
            for key in list(self.map):
                record = self.record(key)
                if record:
                    self._own(key, record)
        self.set_app_icon()

    def _icon_attachment(self):
        """ The icon of the module in Apps: a file of the module, served as Odoo serves
        the static files of an imported module. """
        attachment = self.record('icon:')
        raw = self.progress._icon_bytes()
        if attachment:
            attachment.write({'raw': raw})
            return
        attachment = self.env['ir.attachment'].sudo().create({
            'name': 'icon.png', 'type': 'binary', 'raw': raw, 'public': True, 'res_model': 'ir.ui.view',
            'url': '/%s/static/description/icon.png' % self.course['module'],
        })
        # created with the module, removed with it
        module_key = 'module:' + self.course['module']
        step_key = next((step for step, entries in self.log.items()
                         if any(entry.get('key') == module_key for entry in entries)), None)
        if step_key:
            self._created(step_key, 'icon:', attachment)

    def _write(self, step_key, record, values):
        old = {}
        for name, value in values.items():
            field = record._fields[name]
            old[name] = field.convert_to_write(record[name], record)
            if field.type == 'many2one':
                old[name] = record[name].id
        if all(old[name] == values[name] for name in values):
            return
        record.write(values)
        self.log.setdefault(step_key, []).append({'do': 'write', 'model': record._name, 'id': record.id, 'old': old})

    #
    # building a step
    #

    def _replacing_fields(self, step):
        """ Mutes the warning on two fields of the same label while a step replaces a field (see above). """
        if any(op['op'] == 'drop_field' for op in (step or {}).get('live') or ()):
            return mute_logger(SAME_LABEL_LOGGER)
        return nullcontext()

    def build(self, index):
        step = self.course['steps'][index]
        with self._replacing_fields(step):
            self._build(step, index)

    def _build(self, step, index):
        step_key = step['key']
        self.log[step_key] = []
        self._sync_module(step_key, index)
        models = models_at(self.course, index)
        ops = step.get('live') or ()
        for op in ops:
            if not op.get('after_xml'):
                getattr(self, '_op_' + op['op'])(step_key, op)
        files = files_at(self.course, index)
        self._sync_accesses(step_key, files, models)
        for _path, record in xml_records(files, paths=set(step.get('files') or ())):
            self._xml_record(step_key, record, models)
        for op in ops:
            if op.get('after_xml'):
                getattr(self, '_op_' + op['op'])(step_key, op)
        self.refresh_module()
        self.save()

    def refresh_module(self):
        """ The Installed Features of the module in Apps (its menus, views, reports):
        Odoo computes them when a module is installed, the app built live grows after. """
        module = self.record('module:' + self.course['module'])
        if not module:
            return
        # the module owns only what still exists, and no field Odoo adds by itself
        for data in self.env['ir.model.data'].sudo().search([('module', '=', module.name)]):
            record = self.env[data.model].sudo().browse(data.res_id).exists() if data.model in self.env else None
            if not record or (data.model == 'ir.model.fields' and not record.name.startswith('x_')):
                data.unlink()
        module._get_views()

    def _field_values(self, op):
        values = {
            'name': live_field(op['name']),
            'field_description': op.get('string') or op['name'],
            'ttype': op['type'],
            'required': bool(op.get('required')),
        }
        if op.get('relation'):
            values['relation'] = self.model_name(op['relation'])
        if op.get('selection'):
            values['selection_ids'] = [(0, 0, {'value': value, 'name': label, 'sequence': sequence})
                                       for sequence, (value, label) in enumerate(op['selection'])]
        if op.get('compute'):
            values.update(compute=op['compute'], depends=op.get('depends') or '', store=False, readonly=True)
        if op.get('group_expand'):
            values['group_expand'] = True
        return values

    def _set_default(self, step_key, model, field_op, field):
        Default = self.env['ir.default'].sudo()
        Default.set(self.model_name(model), live_field(field_op['name']), field_op['default'])
        default = Default.search([('field_id', '=', field.id), ('user_id', '=', False),
                                  ('company_id', '=', False)], limit=1)
        if default:
            self._created(step_key, 'default:%s.%s' % (model, field_op['name']), default)

    def _already_built(self, key, name):
        """ Another learner built this app live in this database, or its module is installed. """
        other = self.env['academy.progress'].sudo().search([
            ('course_key', '=', self.progress.course_key), ('id', '!=', self.progress.id)])
        built_by = other.filtered(lambda progress: key in (progress.live_map or {}))
        if not built_by and key.startswith('module:'):
            raise UserError(str(_lt(
                "The module %(module)s is installed in this database: uninstall it from Apps to "
                "build the app live, or go on in Code it.")) % {'module': name})
        raise UserError(str(_lt(
            "%(model)s already exists in this database: %(who)s built this app live. Each "
            "database holds one live build of a course: start the course over in their name, "
            "or learn on another database.")) % {
                'model': name, 'who': ', '.join(built_by.user_id.mapped('name')) or str(_lt("someone")),
            })

    def _op_model(self, step_key, op):
        if live_model(op['model']) in self.env.registry:
            self._already_built('model:' + op['model'], live_model(op['model']))
        values = {
            'name': op['string'],
            'model': live_model(op['model']),
            'info': 'Built live with the Odoo Mates Academy: in a module, this is %s.' % op['model'],
            'field_id': [(0, 0, self._field_values(field)) for field in op['fields']],
        }
        if op.get('order'):
            values['order'] = ', '.join(' '.join([live_field(part.split()[0])] + part.split()[1:])
                                        if part.split()[0] != 'id' else part
                                        for part in (part.strip() for part in op['order'].split(',')))
        if op.get('fold_name'):
            values['fold_name'] = live_field(op['fold_name'])
        model = self.env['ir.model'].sudo().create(values)
        self._created(step_key, 'model:' + op['model'], model)
        for field in model.field_id.filtered(lambda field: field.name.startswith('x_')):
            # the fields of the course; the ones Odoo adds to every model are Odoo's
            name = field.name[2:]
            key = 'field:%s.%s' % (op['model'], name)
            self.map[key] = ['ir.model.fields', field.id]
            self._own(key, field)
        for field_op in op['fields']:
            if 'default' in field_op:
                field = self.record('field:%s.%s' % (op['model'], field_op['name']))
                self._set_default(step_key, op['model'], field_op, field)

    def _op_field(self, step_key, op):
        model = self.ir_model(op['model'])
        field = self.env['ir.model.fields'].sudo().create(dict(self._field_values(op), model_id=model.id))
        self._created(step_key, 'field:%s.%s' % (op['model'], op['name']), field)
        if 'default' in op:
            self._set_default(step_key, op['model'], op, field)

    def _op_drop_field(self, step_key, op):
        key = 'field:%s.%s' % (op['model'], op['name'])
        field = self.record(key)
        if not field:
            return
        self._unlink(step_key, key, ('name', 'field_description', 'ttype', 'required', 'model_id'))

    def _op_method(self, step_key, op):
        key = 'method:%s.%s' % (op['model'], op['name'])
        action = self.record(key)
        if action:
            self._write(step_key, action, {'code': op['code'], 'name': op['string']})
            return
        model = self.ir_model(op['model'])
        action = self.env['ir.actions.server'].sudo().create({
            'name': op['string'], 'model_id': model.id, 'state': 'code', 'code': op['code'],
        })
        self._created(step_key, key, action)

    def _op_mail_thread(self, step_key, op):
        """ The model inherits mail.thread. Odoo never unticks it: not logged, so
        that undoing the step leaves it (the view goes back without the chatter). """
        model = self.ir_model(op['model'])
        if 'is_mail_thread' not in model._fields:
            raise UserError(str(_lt("This step needs Discuss: pick Basic + a little more again, "
                                    "the Academy installs it.")))
        if not model.is_mail_thread:
            model.sudo().write({'is_mail_thread': True})

    def _op_tracking(self, step_key, op):
        for name in op['fields']:
            field = self.record('field:%s.%s' % (op['model'], name))
            if field:
                self._write(step_key, field, {'tracking': 100})
        # mail caches the tracked fields of a model
        self.env.transaction.invalidate_ormcache()

    def _sync_accesses(self, step_key, files, models):
        """ The access rights of the CSV file, as it is after the step: new lines
        created, changed ones written, removed ones deleted. """
        accesses = csv_accesses(files)
        for access in accesses:
            group = self.resolve(access['group']) if access['group'] else None
            values = {
                'name': access['name'],
                'model_id': self.ir_model(access['model']).id,
                'group_id': group.id if group else False,
                'operation': access['operation'],
                'domain': self.convert_expr(access['domain'], access['model'], models) if access['domain'] else False,
            }
            existing = self.record(access['xmlid'])
            if existing:
                self._write(step_key, existing, values)
            else:
                self._created(step_key, access['xmlid'], self.env['ir.access'].sudo().create(values))
        kept = {access['xmlid'] for access in accesses}
        for key, (model, _id) in list(self.map.items()):
            if model == 'ir.access' and key not in kept:
                self._unlink(step_key, key, ('name', 'model_id', 'group_id', 'operation', 'domain'))

    def resolve(self, ref):
        """ A record named in the files: an id of the module, or an id of Odoo. """
        return self.env.ref(ref) if '.' in ref else self.record(ref)

    def _unlink(self, step_key, key, names):
        """ Remove a record built earlier, keeping what recreates it on undo. """
        record = self.record(key)
        if not record:
            return
        values = {}
        for name in names:
            value = record[name]
            values[name] = value.id if hasattr(value, '_name') and record._fields[name].type == 'many2one' else value
        self.log.setdefault(step_key, []).append({'do': 'unlink', 'model': record._name, 'key': key, 'values': values})
        record.unlink()
        self.map.pop(key, None)

    def _xml_record(self, step_key, record, models):
        handler = {
            'ir.ui.view': self._view_values,
            'ir.actions.act_window': self._action_values,
            'ir.ui.menu': self._menu_values,
        }.get(record['model'], self._generic_values)
        if record['model'] in self.created_models:
            handler = self._data_values
        values = handler(record, models)
        existing = self.record(record['xmlid'])
        if existing:
            self._write(step_key, existing, values)
            return
        created = self.env[self.model_name(record['model'])].sudo().create(values)
        self._created(step_key, record['xmlid'], created)
        if record['model'] == 'ir.ui.menu' and not record['values'].get('parent'):
            self.set_app_icon(created)
        if record['model'] in ('res.groups', 'res.groups.privilege') or record.get('template'):
            # views name groups by external id: give the group one
            Data = self.env['ir.model.data'].sudo()
            Data.search([('module', '=', LIVE_MODULE), ('name', '=', record['xmlid'])]).unlink()
            data = Data.create({'module': LIVE_MODULE, 'name': record['xmlid'], 'model': created._name,
                                'res_id': created.id, 'noupdate': True})
            self._created(step_key, 'xmlid:' + record['xmlid'], data)

    def _local(self, ref):
        """ An id of the learner's module without its prefix: learn_todo.x is x. """
        prefix = self.course['module'] + '.'
        return ref[len(prefix):] if ref.startswith(prefix) else ref

    def _live_groups(self, groups):
        """ groups="..." of a view, naming the groups built live. """
        refs = []
        for ref in groups.split(','):
            ref = ref.strip()
            negate = '!' if ref.startswith('!') else ''
            ref = self._local(ref.lstrip('!'))
            refs.append(negate + (ref if '.' in ref else '%s.%s' % (LIVE_MODULE, ref)))
        return ','.join(refs)

    def set_app_icon(self, menus=None):
        """ The learner's icon on the app built live: its menus without a parent,
        and its module in Apps. """
        if menus is None and self.record('module:' + self.course['module']):
            self._icon_attachment()
        if menus is None:
            menus = self.env['ir.ui.menu'].sudo()
            for key, (model, _id) in self.map.items():
                if model == 'ir.ui.menu':
                    menus |= self.record(key) or menus.browse()
            menus = menus.filtered(lambda menu: not menu.parent_id)
        if not menus:
            return
        if self.progress.icon == 'custom' and self.progress.icon_attachment_id:
            menus.write({'web_icon': False})
            menus.write({'web_icon_data': BinaryBytes(self.progress._icon_bytes())})
        else:
            menus.write({'web_icon': 'om_academy,%s' % self.progress._icon_url().split('/om_academy/', 1)[1]})

    def _live_ref(self, ref):
        """ An id of the learner's module, as built live: om_academy_live.x """
        local = self._local(ref)
        return '%s.%s' % (LIVE_MODULE, local) if '.' not in local else ref

    def _view_values(self, record, models):
        values = record['values']
        if record.get('template'):
            arch = etree.fromstring(values['arch'])
            for node in arch.iter(tag=etree.Element):
                if node.get('t-call') and node.get('t-call').startswith(self.course['module'] + '.'):
                    node.set('t-call', self._live_ref(node.get('t-call')))
            arch.set('t-name', self._live_ref(record['xmlid']))
            return {'name': values['name'], 'type': 'qweb', 'arch': etree.tostring(arch, encoding='unicode'),
                    'key': self._live_ref(record['xmlid'])}
        values = record['values']
        model = values['model']
        result = {
            'name': values['name'],
            'model': self.model_name(model),
            'arch': self.convert_arch(values['arch'], model, models),
        }
        if isinstance(values.get('inherit_id'), dict):
            result['inherit_id'] = self.env.ref(values['inherit_id']['ref']).id
        return result

    def _action_values(self, record, models):
        values = record['values']
        result = {'name': values['name'], 'res_model': self.model_name(values['res_model']),
                  'view_mode': values.get('view_mode') or 'list,form'}
        for name in ('domain', 'context'):
            if values.get(name):
                result[name] = self.convert_expr(values[name], values['res_model'], models)
        return result

    def _generic_values(self, record, models):
        """ A record of the files as Odoo loads it: text converted to the field's
        type, ref= to the record, and eval= of links to records. """
        Model = self.env[record['model']]
        result = {}
        for name, value in record['values'].items():
            field = Model._fields[name]
            if isinstance(value, dict) and 'ref' in value:
                result[name] = self.resolve(value['ref']).id
            elif isinstance(value, dict) and 'eval' in value:
                result[name] = [(4, self.resolve(ref).id) for ref in re.findall(r"ref\('([^']+)'\)", value['eval'])]
            elif field.type == 'integer':
                result[name] = int(value)
            elif field.type == 'float':
                result[name] = float(value)
            elif isinstance(value, str) and value.startswith(self.course['module'] + '.'):
                result[name] = self._live_ref(value)  # report_name: the template built live
            else:
                result[name] = value
        return result

    def _data_values(self, record, models):
        """ A record of a model of the course, from a data file: its fields are x_ ones. """
        Model = self.env[self.model_name(record['model'])]
        result = {}
        for name, value in record['values'].items():
            field = Model._fields[live_field(name)]
            if isinstance(value, dict) and 'eval' in value:
                value = {'True': True, 'False': False}.get(value['eval'], value['eval'])
            elif isinstance(value, dict) and 'ref' in value:
                value = self.resolve(value['ref']).id
            elif field.type == 'integer':
                value = int(value)
            result[live_field(name)] = value
        return result

    def _menu_values(self, record, models):
        values = record['values']
        result = {'name': values['name'], 'sequence': int(values.get('sequence') or 10)}
        parent = self.record(values['parent']) if values.get('parent') else None
        result['parent_id'] = parent.id if parent else False
        if values.get('action'):
            action = self.record(values['action'])
            result['action'] = '%s,%d' % (action._name, action.id)
        if values.get('groups'):
            result['group_ids'] = [(6, 0, [self.resolve(self._local(ref.strip())).id
                                           for ref in values['groups'].split(',')])]
        return result

    def _names_pattern(self, model, models):
        names = set(models.get(model, {}).get('fields', ()))
        if not names:
            return None
        return re.compile(r'(?<![\w.])(%s)(?![\w])' % '|'.join(map(re.escape, sorted(names, key=len, reverse=True))))

    def convert_expr(self, text, model, models):
        """ A domain or a condition, with the live names of the course's fields. """
        pattern = self._names_pattern(model, models)
        return pattern.sub(lambda match: live_field(match.group(1)), text) if pattern else text

    def convert_arch(self, arch, model, models):
        """ The arch of a module view, for the custom model: x_ field names, and
        server actions in place of the methods its buttons call. """
        names = set(models.get(model, {}).get('fields', ()))
        pattern = self._names_pattern(model, models)
        root = etree.fromstring(arch)
        for node in root.iter(tag=etree.Element):
            if node.tag == 'field' and node.get('name') in names:
                node.set('name', live_field(node.get('name')))
            if node.tag == 'button' and node.get('type') == 'object':
                action = self.record('method:%s.%s' % (model, node.get('name')))
                if action:
                    node.set('type', 'action')
                    node.set('name', str(action.id))
            if node.get('groups'):
                node.set('groups', self._live_groups(node.get('groups')))
            for attribute in MODIFIER_ATTRIBUTES:
                if pattern and node.get(attribute):
                    node.set(attribute, pattern.sub(lambda match: live_field(match.group(1)), node.get(attribute)))
        return etree.tostring(root, encoding='unicode')

    #
    # undoing a step
    #

    def _restore_views(self, step_key):
        """ The views as the course built them at this step: the learner may have
        changed them in Odoo (Your turn), with fields the undo removes. """
        index = next((index for index, step in enumerate(self.course['steps']) if step['key'] == step_key), None)
        if index is None:
            return
        models = models_at(self.course, index)
        for _path, record in xml_records(files_at(self.course, index)):
            view = self.record(record['xmlid']) if record['model'] == 'ir.ui.view' and not record.get('template') else None
            if view:
                arch = self.convert_arch(record['values']['arch'], record['values']['model'], models)
                if etree.tostring(etree.fromstring(view.arch)) != etree.tostring(etree.fromstring(arch)):
                    view.write({'arch': arch})

    def undo(self, step_key):
        step = next((step for step in self.course['steps'] if step['key'] == step_key), None)
        with self._replacing_fields(step):
            self._undo(step_key)

    def _undo(self, step_key):
        self._restore_views(step_key)
        for entry in reversed(self.log.pop(step_key, [])):
            if entry['do'] == 'create':
                record = self.env[entry['model']].sudo().browse(entry['id']).exists()
                if record and record._name == 'ir.module.module':
                    record.state = 'uninstalled'  # Odoo removes no installed module
                if record:
                    record.unlink()
                self.map = {key: value for key, value in self.map.items()
                            if value != [entry['model'], entry['id']]}
                if entry['model'] == 'ir.model':
                    prefix = 'field:%s.' % entry['key'].split(':', 1)[1]
                    self.map = {key: value for key, value in self.map.items() if not key.startswith(prefix)}
            elif entry['do'] == 'write':
                record = self.env[entry['model']].sudo().browse(entry['id']).exists()
                if record:
                    record.write(entry['old'])
                    if 'tracking' in entry['old']:
                        self.env.transaction.invalidate_ormcache()
            elif entry['do'] == 'unlink':
                record = self.env[entry['model']].sudo().create(entry['values'])
                self.map[entry['key']] = [record._name, record.id]
                self._own(entry['key'], record)
            elif entry['do'] == 'drop':
                # a field dropped by an earlier version of the Academy
                field = self.env['ir.model.fields'].sudo().create(entry['values'])
                self.map[entry['key']] = ['ir.model.fields', field.id]
        self.refresh_module()
        self.save()
