# The learner's module as a course step leaves it: its files, the records its
# XML and CSV files declare, and the models its Python files define.
import ast
import csv
import difflib
import io

from lxml import etree

# in the files of a course: the icon the learner picks, an image (bytes) once personalized
ICON = '<the icon of your app>'
ICON_PATH = 'static/description/icon.png'


def files_at(course, index):
    """ {path: content} of the module after step ``index``. """
    files = {}
    for step in course['steps'][:index + 1]:
        files.update(step.get('files') or {})
    return files


def changed_lines(course, index, path):
    """ The line numbers (from 0) the step adds or changes in ``path``. """
    before = files_at(course, index - 1).get(path) if index else None
    after = course['steps'][index]['files'][path]
    if not isinstance(after, str):
        return set()
    if before is None:
        return set(range(len(after.splitlines())))
    new = set()
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ('replace', 'insert'):
            new.update(range(j1, j2))
    return new


def manifest_data(files):
    manifest = files.get('__manifest__.py')
    return list(ast.literal_eval(manifest).get('data', [])) if manifest else []


def xml_records(files, paths=None):
    """ [(path, record)] for the records of the XML data files, in manifest order.

    A record: {'xmlid', 'model', 'values'}; a menuitem has model 'ir.ui.menu'.
    """
    records = []
    for path in manifest_data(files):
        if not path.endswith('.xml') or (paths is not None and path not in paths):
            continue
        root = etree.fromstring(files[path].encode())
        for node in root:
            if not isinstance(node.tag, str):
                continue
            if node.tag == 'record':
                values = {}
                for field in node.findall('field'):
                    if field.get('ref'):
                        values[field.get('name')] = {'ref': field.get('ref')}
                    elif field.get('eval'):
                        values[field.get('name')] = {'eval': field.get('eval')}
                    elif field.get('type') == 'xml':
                        values[field.get('name')] = ''.join(
                            etree.tostring(child, encoding='unicode') for child in field).strip()
                    else:
                        values[field.get('name')] = (field.text or '').strip()
                records.append((path, {'xmlid': node.get('id'), 'model': node.get('model'), 'values': values}))
            elif node.tag == 'template':
                # a QWeb template: a view of type qweb, as Odoo loads it
                inner = (node.text or '') + ''.join(etree.tostring(child, encoding='unicode') for child in node)
                arch = '<t t-name="%s">%s</t>' % (node.get('id'), inner)
                records.append((path, {'xmlid': node.get('id'), 'model': 'ir.ui.view', 'template': True,
                                       'values': {'name': node.get('id'), 'type': 'qweb', 'arch': arch}}))
            elif node.tag == 'menuitem':
                values = {key: node.get(key) for key in ('name', 'parent', 'action', 'sequence', 'web_icon',
                                                         'groups') if node.get(key)}
                records.append((path, {'xmlid': node.get('id'), 'model': 'ir.ui.menu', 'values': values}))
    return records


def csv_accesses(files):
    """ The access rights of the CSV data files: [{'xmlid', 'name', 'model', 'group', 'operation'}]. """
    accesses = []
    for path in manifest_data(files):
        if not path.endswith('ir.access.csv'):
            continue
        for row in csv.DictReader(io.StringIO(files[path])):
            accesses.append({
                'xmlid': row['id'], 'name': row['name'], 'model': row['model_id'],
                'group': row.get('group_id/id') or False, 'operation': row['operation'],
                'domain': row.get('domain') or False,
            })
    return accesses


def models_at(course, index):
    """ {model: {'string', 'fields': {name: spec}, 'methods': {name: spec}}} after step ``index``,
    from the Python part of the steps. """
    models = {}
    for step in course['steps'][:index + 1]:
        for op in step.get('live') or ():
            if op['op'] == 'model':
                models[op['model']] = {
                    'string': op['string'],
                    'fields': {field['name']: field for field in op['fields']},
                    'methods': {},
                }
            elif op['op'] == 'field':
                # a field added to a model of Odoo (res.partner) creates its entry
                models.setdefault(op['model'], {'string': None, 'fields': {}, 'methods': {}, 'existing': True})
                models[op['model']]['fields'][op['name']] = op
            elif op['op'] == 'drop_field':
                models[op['model']]['fields'].pop(op['name'], None)
            elif op['op'] == 'method':
                models.setdefault(op['model'], {'string': None, 'fields': {}, 'methods': {}, 'existing': True})
                models[op['model']]['methods'][op['name']] = op
    return models



def course_models(course):
    """ The models a course creates (a model of Odoo it extends is not one). """
    return {op['model'] for step in course['steps'] for op in step.get('live') or () if op['op'] == 'model'}
