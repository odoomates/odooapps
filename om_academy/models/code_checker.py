# Code it: does the learner's module, as Odoo loaded it, hold what the step
# asks for? The expectations come from the course files themselves: the
# models and fields of the Python part, and every record of the XML and CSV
# files, compared with what Odoo has under the module's external ids.
import ast
import os
import re
import sys

import psutil
from lxml import etree

from odoo.modules.module import get_module_path
from odoo.tools.translate import LazyTranslate

from .course_files import csv_accesses, files_at, models_at, xml_records

_lt = LazyTranslate(__name__)

FIELD_TYPES = {'char': 'Char', 'date': 'Date', 'many2one': 'Many2one', 'selection': 'Selection',
               'integer': 'Integer', 'boolean': 'Boolean', 'text': 'Text'}


class CodeChecker:

    def __init__(self, env, course):
        self.env = env
        self.course = course
        self.module = course['module']
        self.results = []

    def ok(self, text, **params):
        self.results.append({'ok': True, 'text': str(text) % params if params else str(text)})

    def fail(self, text, hint=None, **params):
        self.results.append({'ok': False, 'text': str(text) % params if params else str(text),
                             'hint': str(hint) if hint else False})

    def check(self, index):
        self.results = []
        if not self._check_module():
            return self.results
        models = models_at(self.course, index)
        for model, spec in models.items():
            self._check_model(model, spec)
        files = files_at(self.course, index)
        for access in csv_accesses(files):
            self._check_access(access)
        for _path, record in xml_records(files):
            self._check_record(record)
        for extra in self.course['steps'][index].get('checks') or ():
            getattr(self, '_check_' + extra['kind'])(extra)
        return self.results

    def _check_module(self):
        module = self.env['ir.module.module'].sudo().search([('name', '=', self.module)])
        if not module:
            self.fail(_lt("Odoo does not know the module %(module)s yet."),
                      _lt("Put the folder in your addons path and click Install: the Academy updates "
                          "the list of apps first."), module=self.module)
            return False
        if module.state != 'installed':
            self.fail(_lt("The module %(module)s is not installed."), _lt("Click Install."), module=self.module)
            return False
        self.ok(_lt("Your module %(module)s is installed."), module=self.module)
        if not module.author:
            self.fail(_lt("Your module has no author: you wrote it, so write your name in it."),
                      _lt("In __manifest__.py, a line 'author': 'Your Name', then Install / Upgrade."))
        else:
            self.ok(_lt("Its author: %(author)s."), author=module.author)
        return True

    def _restart_hint(self, model):
        """ Why a model or a field may be missing although the file holds it. """
        path = get_module_path(self.module)
        python_file = os.path.join(path, 'models', model.replace('.', '_') + '.py') if path else None
        if not python_file or not os.path.isfile(python_file):
            return _lt("Check the file, and the import lines of both __init__.py files.")
        package = 'odoo.addons.%s.models.%s' % (self.module, model.replace('.', '_'))
        started = psutil.Process().create_time()
        if package not in sys.modules or os.path.getmtime(python_file) > started:
            return _lt("Your file is newer than what Odoo loaded: restart Odoo, then click Upgrade.")
        return _lt("Check the file, and the import lines of both __init__.py files, then click Upgrade.")

    def _check_model(self, model, spec):
        if model not in self.env.registry:
            self.fail(_lt("The model %(model)s does not exist."), self._restart_hint(model), model=model)
            return
        self.ok(_lt("The model %(model)s exists."), model=model)
        Model = self.env[model]
        for name, field_spec in spec['fields'].items():
            field = Model._fields.get(name)
            label = '%s.%s' % (model, name)
            if field is None:
                self.fail(_lt("The field %(field)s is missing."), self._restart_hint(model), field=label)
                continue
            if field.type != field_spec['type']:
                self.fail(_lt("The field %(field)s is a %(found)s: it should be a %(expected)s."),
                          field=label, found=FIELD_TYPES.get(field.type, field.type),
                          expected=FIELD_TYPES.get(field_spec['type'], field_spec['type']))
                continue
            if field_spec.get('required') and not field.required:
                self.fail(_lt("The field %(field)s should be required: add required=True."), field=label)
                continue
            if field_spec.get('relation') and field.comodel_name != field_spec['relation']:
                self.fail(_lt("The field %(field)s should link to %(relation)s."),
                          field=label, relation=field_spec['relation'])
                continue
            if field_spec.get('selection'):
                values = field.get_values(self.env)
                missing = [value for value, _label in field_spec['selection'] if value not in values]
                if missing:
                    self.fail(_lt("The field %(field)s lacks the values %(values)s."),
                              field=label, values=', '.join(missing))
                    continue
            self.ok(_lt("The field %(field)s is right."), field=label)
        for name in spec['methods']:
            if callable(getattr(type(Model), name, None)):
                self.ok(_lt("The method %(method)s exists."), method='%s.%s()' % (model, name))
            else:
                self.fail(_lt("The method %(method)s is missing."), self._restart_hint(model),
                          method='%s.%s()' % (model, name))

    def _check_ref(self, xmlid, model, label):
        record = self.env.ref('%s.%s' % (self.module, xmlid), raise_if_not_found=False)
        if not record or record._name != model:
            self.fail(_lt("Odoo has no %(what)s %(xmlid)s."),
                      _lt("Check the id in the file and the file's line in the manifest, then Upgrade."),
                      what=label, xmlid=xmlid)
            return None
        self.ok(_lt("The %(what)s %(xmlid)s is loaded."), what=label, xmlid=xmlid)
        return record

    def _check_access(self, access):
        found = self._check_ref(access['xmlid'], 'ir.access', _lt("access right"))
        if not found:
            return
        if found.operation != access['operation']:
            self.fail(_lt("The access right %(xmlid)s allows %(found)s: the step asks for %(expected)s."),
                      xmlid=access['xmlid'], found=found.operation, expected=access['operation'])
        expected = ''.join((access['domain'] or '').split())
        if ''.join((found.domain or '').split()) != expected:
            self.fail(_lt("The domain of the access right %(xmlid)s should be %(domain)s."),
                      xmlid=access['xmlid'], domain=access['domain'] or _lt("empty"))

    def _check_record(self, record):
        labels = {'ir.ui.view': _lt("view"), 'ir.actions.act_window': _lt("action"), 'ir.ui.menu': _lt("menu"),
                  'res.groups': _lt("group"), 'res.groups.privilege': _lt("privilege"),
                  'ir.actions.report': _lt("report"), 'report.paperformat': _lt("paper format")}
        if record.get('template'):
            labels['ir.ui.view'] = _lt("template")
        found = self._check_ref(record['xmlid'], record['model'], labels.get(record['model'], record['model']))
        if not found:
            return
        values = record['values']
        if record['model'] == 'ir.ui.view':
            expected = etree.fromstring(values['arch'])
            actual = etree.fromstring(found.arch_db or found.arch)
            if any(expected.iter('chatter')) and not any(actual.iter('chatter')):
                self.fail(_lt("The view %(xmlid)s has no chatter."), _lt("Add <chatter/> after </sheet>."),
                          xmlid=record['xmlid'])
            for tag in ('field', 'button'):
                wanted = {node.get('name') for node in expected.iter(tag)}
                present = {node.get('name') for node in actual.iter(tag)}
                for name in sorted(wanted - present):
                    self.fail(_lt("The view %(xmlid)s lacks the %(tag)s %(name)s."),
                              xmlid=record['xmlid'], tag=tag, name=name)
                groups = {node.get('name'): node.get('groups') for node in actual.iter(tag)}
                for node in expected.iter(tag):
                    name = node.get('name')
                    if node.get('groups') and name in groups and \
                            self._groups(groups[name]) != self._groups(node.get('groups')):
                        self.fail(_lt("The %(tag)s %(name)s of the view %(xmlid)s should be for %(groups)s only."),
                                  _lt("Add groups=\"%(groups)s\" to it, then Upgrade.") % {'groups': node.get('groups')},
                                  tag=tag, name=name, xmlid=record['xmlid'], groups=node.get('groups'))
        elif record['model'] == 'ir.actions.act_window' and found.res_model != values['res_model']:
            self.fail(_lt("The action %(xmlid)s opens %(found)s instead of %(expected)s."),
                      xmlid=record['xmlid'], found=found.res_model, expected=values['res_model'])
        elif record['model'] == 'ir.ui.menu' and values.get('web_icon') and found.web_icon != values['web_icon']:
            self.fail(_lt("The menu %(xmlid)s should show the icon %(icon)s."),
                      _lt("Add web_icon=\"%(icon)s\" to the menu, then Upgrade.") % {'icon': values['web_icon']},
                      xmlid=record['xmlid'], icon=values['web_icon'])
        elif record['model'] == 'ir.ui.menu' and values.get('groups') and \
                {self._group(ref) for ref in values['groups'].split(',')} != set(found.group_ids):
            self.fail(_lt("The menu %(xmlid)s should be for %(groups)s only."),
                      _lt("Add groups=\"%(groups)s\" to the menu, then Upgrade.") % {'groups': values['groups']},
                      xmlid=record['xmlid'], groups=values['groups'])
        elif record['model'] == 'ir.ui.menu' and values.get('parent'):
            parent = self.env.ref('%s.%s' % (self.module, values['parent']), raise_if_not_found=False)
            if parent and found.parent_id != parent:
                self.fail(_lt("The menu %(xmlid)s should be under %(parent)s."),
                          xmlid=record['xmlid'], parent=values['parent'])

    def _read(self, path):
        """ The learner's file, as it is on disk: None when it is not there. """
        root = get_module_path(self.module)
        full = os.path.join(root, path) if root else None
        if not full or not os.path.isfile(full):
            return None
        with open(full, encoding='utf-8') as handle:
            return handle.read()

    def _check_files(self, extra):
        """ A file of the module holds what the step writes in it (JavaScript, templates). """
        content = self._read(extra['path'])
        if content is None:
            self.fail(_lt("The file %(path)s is missing."), _lt("Create it, or click Write it for me."),
                      path=extra['path'])
            return
        flat = re.sub(r'\s+', ' ', content)
        missing = [needle for needle in extra['needles'] if re.sub(r'\s+', ' ', needle) not in flat]
        if missing:
            self.fail(_lt("%(path)s lacks %(code)s."), _lt("Compare your file with the code of the step."),
                      path=extra['path'], code=', '.join(missing))
        else:
            self.ok(_lt("%(path)s is right."), path=extra['path'])

    def _check_assets(self, extra):
        """ The manifest puts the files of static/src in a bundle the browser loads. """
        content = self._read('__manifest__.py')
        try:
            manifest = ast.literal_eval(content) if content else {}
        except (SyntaxError, ValueError):
            manifest = {}
        bundles = manifest.get('assets') or {}
        if any('%s/static/src' % self.module in str(item) for item in bundles.get(extra['bundle']) or ()):
            self.ok(_lt("The manifest loads static/src in %(bundle)s."), bundle=extra['bundle'])
        else:
            self.fail(_lt("The manifest does not load static/src in %(bundle)s."),
                      _lt("Add the 'assets' of the step to __manifest__.py, then restart Odoo."),
                      bundle=extra['bundle'])

    def _check_mail_thread(self, extra):
        model = extra['model']
        if model not in self.env.registry:
            return
        if 'mail.thread' in self.env.registry and isinstance(self.env[model], self.env.registry['mail.thread']):
            self.ok(_lt("%(model)s inherits mail.thread: it has a chatter."), model=model)
        else:
            self.fail(_lt("%(model)s does not inherit mail.thread."),
                      _lt("Add _inherit = ['mail.thread'] and 'mail' to the depends of the manifest, "
                          "restart Odoo, then Upgrade."), model=model)

    def _check_tracking(self, extra):
        model = extra['model']
        if model not in self.env.registry:
            return
        for name in extra['fields']:
            field = self.env[model]._fields.get(name)
            label = '%s.%s' % (model, name)
            if field is not None and getattr(field, 'tracking', None):
                self.ok(_lt("%(field)s is tracked."), field=label)
            else:
                self.fail(_lt("%(field)s is not tracked."), _lt("Add tracking=True to the field."), field=label)

    def _group(self, ref):
        ref = ref.strip()
        return self.env.ref(ref if '.' in ref else '%s.%s' % (self.module, ref), raise_if_not_found=False)

    def _groups(self, groups):
        """ The groups="..." of a view, as records: the module's own ids may be written with or without it. """
        return {self._group(ref) for ref in (groups or '').split(',') if ref.strip()}

    def _check_compute(self, extra):
        model = extra['model']
        if model not in self.env.registry or extra['field'] not in self.env[model]._fields:
            return
        field = self.env[model]._fields[extra['field']]
        label = '%s.%s' % (model, extra['field'])
        if not field.compute:
            self.fail(_lt("The field %(field)s is not computed: add compute='...'."), field=label)
            return
        depends = set(self.env.registry.field_depends.get(field, ()))
        missing = [name for name in extra['depends'] if name not in depends]
        if missing:
            self.fail(_lt("%(field)s does not depend on %(names)s: Odoo will not recompute it when "
                          "they change."), _lt("Add them to @api.depends(...)."),
                      field=label, names=', '.join(missing))
            return
        self.ok(_lt("%(field)s is computed, and recomputed when its fields change."), field=label)
