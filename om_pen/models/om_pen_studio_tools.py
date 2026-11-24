""" Translations, health check, and export / import of everything made in the Studio.

The export is a real Odoo module: installing it on another database recreates the
models, fields, views, actions, menus, reports, access rights and automations. It also
carries a studio.json, which Pen reads when the module is imported back, so the views
stay editable in the Studio there.
"""
import base64
import io
import json
import re
import zipfile

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes
from odoo.tools.convert import convert_xml_import

from .om_pen_view import KEY_PREFIX

EXPORT_MODULE = 'om_pen_studio_export'
IMPORT_MODULE = '__om_pen__'
MANIFEST = '''{
    'name': %(name)r,
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': "Everything made in Pen Studio on %(database)s",
    'author': 'Odoo Mates',
    'depends': %(depends)r,
    'data': ['data/studio.xml'],
    'license': 'LGPL-3',
}
'''
# what is written of each model, in the order the records are created
EXPORTED = {
    'res.groups': ('name', 'comment'),
    'ir.model': ('name', 'model', 'state', 'is_mail_thread', 'is_mail_activity'),
    'ir.model.fields': ('name', 'model', 'model_id', 'ttype', 'field_description', 'relation', 'relation_field',
                        'required', 'readonly', 'store', 'help', 'compute', 'depends', 'related', 'currency_field',
                        'on_delete', 'group_expand', 'copied', 'index', 'domain', 'state'),
    'ir.model.fields.selection': ('field_id', 'value', 'name', 'sequence'),
    'ir.access': ('name', 'model_id', 'group_id', 'operation', 'domain', 'active'),
    'ir.ui.view': ('name', 'key', 'model', 'type', 'mode', 'priority', 'inherit_id', 'arch'),
    'ir.actions.act_window': ('name', 'res_model', 'view_mode', 'domain', 'context', 'help', 'search_view_id'),
    'ir.actions.server': ('name', 'model_id', 'state', 'update_path', 'evaluation_type', 'value', 'code',
                          'template_id', 'activity_type_id', 'activity_summary', 'activity_date_deadline_range',
                          'activity_date_deadline_range_type', 'activity_user_type', 'activity_user_id',
                          'log_note_note'),
    'ir.actions.report': ('name', 'model', 'report_type', 'report_name', 'print_report_name', 'paperformat_id',
                          'binding_model_id', 'binding_type'),
    'ir.ui.menu': ('name', 'parent_id', 'sequence', 'action', 'web_icon_data'),
    'ir.default': ('field_id', 'json_value'),
    'base.automation': ('name', 'model_id', 'trigger', 'filter_domain', 'filter_pre_domain', 'trigger_field_ids',
                        'trg_date_id', 'trg_date_range', 'trg_date_range_type', 'action_server_ids', 'active'),
}


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    # ------------------------------------------------------------------
    # translations
    # ------------------------------------------------------------------

    @api.model
    def studio_translations(self, customization_id):
        """ The texts of the published view and of the model's custom fields, per language. """
        customization = self._customization(customization_id)
        langs = self.env['res.lang'].get_installed()
        rows = []
        view = customization.custom_view_id
        if view:
            terms, _context = view.get_field_translations('arch_db')
            by_source = {}
            for term in terms:
                by_source.setdefault(term['source'], {})[term['lang']] = term['value']
            for source, values in by_source.items():
                if source.strip():
                    rows.append({'kind': 'view', 'id': view.id, 'source': source, 'values': values})
        for field in self.env['ir.model.fields'].search([('model', '=', customization.model), ('state', '=', 'manual')]):
            terms, _context = field.get_field_translations('field_description')
            rows.append({'kind': 'field', 'id': field.id, 'source': field.with_context(lang='en_US').field_description,
                         'values': {term['lang']: term['value'] for term in terms}})
        return {'langs': [[code, name] for code, name in langs], 'rows': rows, 'published': bool(view)}

    @api.model
    def studio_translation_save(self, kind, record_id, lang, source, value):
        self._check()
        if kind == 'view':
            view = self.env['ir.ui.view'].sudo().browse(int(record_id))
            if not (view.key or '').startswith(KEY_PREFIX):
                raise UserError(_("Only the views made in the Studio are translated here."))
            view.update_field_translations('arch_db', {lang: {source: value}})
        else:
            self._check_admin()
            field = self.env['ir.model.fields'].sudo().browse(int(record_id))
            if field.state != 'manual':
                raise UserError(_("Only custom fields are translated here."))
            field.update_field_translations('field_description', {lang: value})
        return True

    # ------------------------------------------------------------------
    # health
    # ------------------------------------------------------------------

    @api.model
    def studio_health(self):
        """ What no longer fits after a module update, in one place. """
        self._check()
        issues = []
        for customization in self.env['om.pen.view'].with_context(active_test=False).search([]):
            label = '%s / %s' % (self.env['ir.model']._get(customization.model).name or customization.model,
                                 customization.view_type)
            try:
                _arch, _view, failed = self._draft_arch(customization)
            except Exception as error:  # noqa: BLE001 - reported, not raised
                issues.append({'kind': 'view', 'id': customization.id, 'label': label, 'model': customization.model,
                               'view_type': customization.view_type, 'problem': str(error)})
                continue
            ops = customization.draft_ops or []
            if failed:
                issues.append({'kind': 'view', 'id': customization.id, 'label': label, 'model': customization.model,
                               'view_type': customization.view_type,
                               'problem': _("%(count)s change(s) no longer fit: %(what)s", count=len(failed),
                                            what=', '.join(ops[index].get('label') or '' for index in failed)),
                               'fixable': True})
            elif customization.broken:
                issues.append({'kind': 'view', 'id': customization.id, 'label': label, 'model': customization.model,
                               'view_type': customization.view_type,
                               'problem': _("The published view points at something the standard view no longer has.")})
        for report in self.env['om.pen.report'].search([]):
            record = self.env[report.model].search([], limit=1) if report.model in self.env else None
            if record is None:
                issues.append({'kind': 'report', 'id': report.id, 'label': report.name,
                               'problem': _("The model %s does not exist any more.", report.model)})
                continue
            if record:
                try:
                    self._render_report(report, record.id)
                except Exception as error:  # noqa: BLE001
                    issues.append({'kind': 'report', 'id': report.id, 'label': report.name, 'model': report.model,
                                   'problem': str(error)[:300]})
        for rule in self.env['om.pen.approval.rule'].search([]):
            if rule.model not in self.env:
                issues.append({'kind': 'approval', 'id': rule.id, 'label': rule.name,
                               'problem': _("The model %s does not exist any more.", rule.model)})
            elif rule.button_type == 'object' and not hasattr(self.env[rule.model], rule.button_name):
                issues.append({'kind': 'approval', 'id': rule.id, 'label': rule.name,
                               'problem': _("The button %s does not exist any more.", rule.button_name)})
        return issues

    @api.model
    def studio_health_fix(self, customization_id):
        """ Drop the unpublished changes that no longer fit, keeping the others. """
        customization = self._customization(customization_id)
        _arch, _view, failed = self._draft_arch(customization)
        kept = [op for index, op in enumerate(customization.draft_ops or []) if index not in failed]
        customization._set_draft(kept)
        return len(failed)

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    @api.model
    def _studio_records(self):
        """ Every record made in the Studio, by model, in creation order.

        The Studio marks what it creates (see om_pen_mark); custom fields named by a
        customization are taken too, so work made before the marks existed comes along.
        """
        marked = {}
        for data in self.env['ir.model.data'].sudo().search([('module', '=', IMPORT_MODULE)]):
            marked.setdefault(data.model, set()).add(data.res_id)

        def taken(model):
            if model not in self.env:
                return None
            Model = self.env[model].sudo().with_context(active_test=False)
            return Model.browse(sorted(marked.get(model, ()))).exists()

        records = {model: (taken(model) if taken(model) is not None else None) for model in EXPORTED}
        records = {model: recs for model, recs in records.items() if recs is not None}
        customizations = self.env['om.pen.view'].with_context(active_test=False).search([])
        reports = self.env['om.pen.report'].search([])
        Fields = self.env['ir.model.fields'].sudo()
        manual_models = records['ir.model'].filtered(lambda m: m.state == 'manual')
        records['ir.model'] = manual_models
        fields_ = records['ir.model.fields'].filtered(lambda f: f.state == 'manual')
        fields_ |= Fields.search([('model_id', 'in', manual_models.ids), ('state', '=', 'manual')])
        named = set()
        for customization in customizations:
            named |= {rule.field_name for rule in customization.rule_ids}
            for operation in (customization.published_ops or []) + (customization.draft_ops or []):
                named |= set(re.findall(r'name="(x_[a-z0-9_]+)"', operation['spec']))
        if named:
            fields_ |= Fields.search([('name', 'in', list(named)), ('state', '=', 'manual')])
        records['ir.model.fields'] = fields_.sorted('id')
        records['ir.model.fields.selection'] = fields_.selection_ids
        records['res.groups'] |= self.env['res.groups'].sudo().search([]).filtered(
            lambda group: (group.get_external_id().get(group.id) or '').startswith('__custom__.om_pen_group'))
        records['ir.ui.view'] = (records['ir.ui.view'] | customizations.custom_view_id | reports.view_id).sorted('id')
        servers = records['ir.actions.server']
        if 'base.automation' in self.env:
            automations = self.env['base.automation'].sudo().with_context(active_test=False).search([]).filtered(
                lambda rule: not rule.get_external_id().get(rule.id))
            records['base.automation'] = automations
            servers |= automations.action_server_ids
        records['ir.actions.server'] = servers
        records['ir.actions.report'] = records['ir.actions.report'] | reports.report_id
        records['ir.ui.menu'] = records['ir.ui.menu'].sorted(lambda menu: (len(menu.parent_path or ''), menu.id))
        records['ir.default'] = self.env['ir.default'].sudo().search([
            ('field_id', 'in', fields_.ids), ('user_id', '=', False), ('company_id', '=', False)])
        return records, customizations

    @api.model
    def _published_specs(self, customizations):
        for customization in customizations:
            for operation in customization.published_ops or []:
                yield operation['spec']

    @api.model
    def studio_export(self):
        """ A zip holding a module with everything made in the Studio. """
        self._check_admin()
        records, customizations = self._studio_records()
        xmlids = {}

        def local_id(record):
            key = (record._name, record.id)
            if key not in xmlids:
                xmlids[key] = '%s_%s' % (record._name.replace('.', '_'), record.id)
            return xmlids[key]

        for model, recs in records.items():
            for record in recs:
                local_id(record)
        depends = set()

        def ref(record):
            if not record:
                return None
            key = (record._name, record.id)
            if key in xmlids:
                return xmlids[key]
            external = record.get_external_id().get(record.id)
            if external and not external.startswith(('__export__', '__custom__', IMPORT_MODULE)):
                depends.add(external.split('.')[0])
                return external
            return None

        root = etree.Element('odoo')
        data = etree.SubElement(root, 'data', noupdate='1')
        files = {}
        for model, recs in records.items():
            for record in recs:
                data.append(self._record_element(record, local_id(record), EXPORTED[model], ref, files))
            if model == 'ir.model.fields':
                # a model is sorted by its own fields: only once they exist
                for ir_model in records['ir.model']:
                    if ir_model.order and ir_model.order != 'id':
                        node = etree.SubElement(data, 'record', id=local_id(ir_model), model='ir.model')
                        etree.SubElement(node, 'field', name='order').text = ir_model.order
        for model in [model for model in records['ir.model'].mapped('model') if model.endswith(('_stage', '_tag'))]:
            for row in self.env[model].sudo().search([]):
                node = etree.SubElement(data, 'record', id='%s_row_%s' % (model.replace('.', '_'), row.id), model=model)
                for name in ('x_name', 'x_sequence', 'x_fold', 'x_color'):
                    if name in row._fields and row[name] not in (False, None):
                        etree.SubElement(node, 'field', name=name).text = str(row[name])
        depends.discard('base')
        depends.discard('__custom__')
        if records.get('base.automation'):
            depends.add('base_automation')
        if any(model.is_mail_thread for model in records['ir.model'] if 'is_mail_thread' in model._fields):
            depends.add('mail')
        studio = self._studio_json(customizations, ref)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('%s/__init__.py' % EXPORT_MODULE, '')
            archive.writestr('%s/__manifest__.py' % EXPORT_MODULE, MANIFEST % {
                'name': _("Pen Studio customizations"),
                'database': self.env.cr.dbname,
                'depends': sorted({'base', 'web'} | depends),
            })
            etree.indent(root, space='    ')
            archive.writestr('%s/data/studio.xml' % EXPORT_MODULE,
                             etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))
            archive.writestr('%s/studio.json' % EXPORT_MODULE, json.dumps(studio, indent=2, default=str))
            for path, content in files.items():
                archive.writestr('%s/%s' % (EXPORT_MODULE, path), content)
        return base64.b64encode(buffer.getvalue()).decode()

    @api.model
    def _record_element(self, record, xmlid, field_names, ref, files):
        node = etree.Element('record', id=xmlid, model=record._name)
        for name in field_names:
            if name not in record._fields:
                continue
            field = record._fields[name]
            value = record[name]
            if field.type == 'many2one':
                target = ref(value)
                if target:
                    etree.SubElement(node, 'field', name=name, ref=target)
            elif field.type == 'many2many':
                refs = [ref(item) for item in value]
                refs = [item for item in refs if item]
                if refs:
                    etree.SubElement(node, 'field', name=name, eval='[(6, 0, [%s])]' % ', '.join(
                        "ref('%s')" % item for item in refs))
            elif field.type == 'reference':
                target = ref(value) if value else None
                if target:
                    etree.SubElement(node, 'field', name=name, ref=target)
            elif name == 'arch':
                element = etree.SubElement(node, 'field', name='arch', type='xml')
                element.append(self._portable_arch(record.arch, ref))
            elif field.type == 'binary':
                if value:
                    # binary data travels as a file of the module
                    path = 'static/data/%s_%s.png' % (xmlid, name)
                    files[path] = bytes(value) if not isinstance(value, str) else base64.b64decode(value)
                    etree.SubElement(node, 'field', name=name, type='base64', file='%s/%s' % (EXPORT_MODULE, path))
            elif field.type == 'boolean':
                etree.SubElement(node, 'field', name=name, eval=str(bool(value)))
            elif value not in (False, None, ''):
                if field.type in ('one2many',):
                    continue
                etree.SubElement(node, 'field', name=name).text = str(value)
        return node

    @api.model
    def _portable_arch(self, arch, ref):
        """ The arch with action ids turned into external ids, valid on any database. """
        tree = etree.fromstring(arch)
        for button in tree.iter('button'):
            if button.get('type') == 'action' and (button.get('name') or '').isdigit():
                action = self.env['ir.actions.actions'].sudo().browse(int(button.get('name'))).exists()
                target = ref(self.env[action.type].sudo().browse(action.id)) if action else None
                if target:
                    button.set('name', '%%(%s)d' % target)
        return tree

    @api.model
    def _studio_json(self, customizations, ref):
        """ What Pen needs to keep the imported work editable. """
        def portable_ops(ops):
            result = []
            for operation in ops or []:
                spec = self._portable_arch(operation['spec'], ref)
                result.append({'spec': etree.tostring(spec, encoding='unicode'), 'label': operation.get('label')})
            return result

        result = {'customizations': [], 'reports': [], 'approvals': []}
        for customization in customizations:
            view_ref = ref(customization.view_id)
            if not view_ref:
                continue
            result['customizations'].append({
                'model': customization.model,
                'view_type': customization.view_type,
                'view': view_ref,
                'generated': ref(customization.custom_view_id),
                'published_ops': portable_ops(customization.published_ops),
                'draft_ops': portable_ops(customization.draft_ops),
            })
        for report in self.env['om.pen.report'].search([]):
            result['reports'].append({
                'name': report.name, 'model': report.model, 'blocks': report.blocks, 'layout': report.layout,
                'report': ref(report.report_id), 'view': ref(report.view_id),
                'inherit_report': ref(report.inherit_report_id), 'position': report.position,
            })
        for rule in self.env['om.pen.approval.rule'].search([]):
            button_name = rule.button_name
            if rule.button_type == 'action' and button_name.isdigit():
                action = self.env['ir.actions.actions'].sudo().browse(int(button_name)).exists()
                button_name = ref(self.env[action.type].sudo().browse(action.id)) if action else button_name
            result['approvals'].append({
                'name': rule.name, 'model': rule.model, 'button_name': button_name, 'button_type': rule.button_type,
                'button_string': rule.button_string, 'group': ref(rule.group_id), 'user': rule.user_id.login or False,
                'domain': rule.domain,
            })
        return result

    # ------------------------------------------------------------------
    # import
    # ------------------------------------------------------------------

    @api.model
    def studio_import(self, content):
        """ Load a module exported from the Studio, and make its work editable here. """
        self._check_admin()
        try:
            archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(content)))
        except (zipfile.BadZipFile, ValueError) as error:
            raise UserError(_("This is not a module exported from Pen Studio.")) from error
        names = archive.namelist()
        xml_name = next((name for name in names if name.endswith('/data/studio.xml')), None)
        json_name = next((name for name in names if name.endswith('/studio.json')), None)
        if not xml_name or not json_name:
            raise UserError(_("This is not a module exported from Pen Studio."))
        tree = etree.fromstring(archive.read(xml_name))
        # binary values are files of the module: set them once the records exist
        binaries = []
        for element in tree.xpath("//field[@type='base64'][@file]"):
            record = element.getparent()
            path = element.get('file').split('/', 1)[1]
            prefix = xml_name.split('/', 1)[0]
            binaries.append((record.get('model'), record.get('id'), element.get('name'), '%s/%s' % (prefix, path)))
            record.remove(element)
        # the export names its records locally; here they live under one module of their own
        local_ids = set(tree.xpath('//record/@id'))
        stream = io.BytesIO(etree.tostring(tree))
        stream.name = xml_name
        convert_xml_import(self.env, IMPORT_MODULE, stream, idref={}, mode='init', noupdate=True)
        for model, xmlid, field_name, path in binaries:
            record = self.env.ref('%s.%s' % (IMPORT_MODULE, xmlid), raise_if_not_found=False)
            if record and path in names:
                record.sudo()[field_name] = BinaryBytes(archive.read(path))
        studio = json.loads(archive.read(json_name))

        def resolve(xmlid):
            if not xmlid:
                return None
            full = xmlid if '.' in xmlid else '%s.%s' % (IMPORT_MODULE, xmlid)
            return self.env.ref(full, raise_if_not_found=False)

        def local_ops(ops):
            result = []
            for operation in ops or []:
                spec = etree.fromstring(operation['spec'])
                for button in spec.iter('button'):
                    match = re.fullmatch(r'%\((.+)\)d', button.get('name') or '')
                    if match:
                        record = resolve(match.group(1))
                        if record:
                            button.set('name', str(record.id))
                result.append({'spec': etree.tostring(spec, encoding='unicode'), 'label': operation.get('label')})
            return result

        View = self.env['om.pen.view']
        count = 0
        for item in studio.get('customizations', []):
            view = resolve(item['view'])
            if not view:
                continue
            customization = View._get_or_create(item['model'], view.id, item['view_type'])
            generated = resolve(item.get('generated'))
            if generated and not customization.custom_view_id:
                # the module brought the generated view: keep it as this customization's
                customization.with_context(om_pen_skip_apply=True).custom_view_id = generated.id
            customization.with_context(om_pen_skip_apply=True).write({
                'published_ops': local_ops(item['published_ops']),
                'draft_ops': local_ops(item['draft_ops']),
            })
            customization._apply()
            count += 1
        for item in studio.get('reports', []):
            if item['model'] not in self.env:
                continue
            report = self.env['om.pen.report'].create({
                'name': item['name'], 'model': item['model'], 'blocks': item['blocks'], 'layout': item['layout'],
                'position': item['position'], 'report_id': (resolve(item['report']) or self.env['ir.actions.report']).id,
                'view_id': (resolve(item['view']) or self.env['ir.ui.view']).id,
                'inherit_report_id': (resolve(item['inherit_report']) or self.env['ir.actions.report']).id,
            })
            report._apply()
        for item in studio.get('approvals', []):
            if item['model'] not in self.env:
                continue
            button_name = item['button_name']
            if item['button_type'] == 'action' and not str(button_name).isdigit():
                action = resolve(button_name)
                button_name = str(action.id) if action else button_name
            group = resolve(item['group'])
            user = self.env['res.users'].search([('login', '=', item['user'])], limit=1) if item['user'] else None
            if not group and not user:
                continue
            self.env['om.pen.approval.rule'].create({
                'name': item['name'], 'model': item['model'], 'button_name': button_name,
                'button_type': item['button_type'], 'button_string': item['button_string'],
                'group_id': group.id if group else False, 'user_id': user.id if user else False,
                'domain': item['domain'],
            })
        return {'records': len(local_ids), 'views': count}
