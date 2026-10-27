""" Charts that travel between databases. The ids a chart holds (a user, an
activity type, an email template, the records an Update or Create step sets)
mean nothing in another database: in a file they become references::

    {'__ref__': 'base.user_admin', 'name': 'Mitchell Admin'}

found again by external id, else by name. What cannot be found is left empty,
for the designer to point out. Ids written inside conditions stay as they are.
"""
import copy

FORMAT = 'om_workflow_template'
VERSION = 1
# the config keys of the nodes that hold a record, and its model
REF_KEYS = {'user_id': 'res.users', 'activity_type_id': 'mail.activity.type', 'template_id': 'mail.template'}
REF = '__ref__'


def _rows_model(env, model, node):
    """ The model the field rows of ``node`` set: the record's, or the one
    a Create step makes. """
    if node['type'] == 'create':
        target = node.get('config', {}).get('model')
        return env.get(target)
    return env[model] if node['type'] == 'update' and model in env else None


def _walk(env, model, graph, convert):
    """ A copy of ``graph`` whose ids went through ``convert(comodel, value)``. """
    graph = copy.deepcopy(graph or {'nodes': [], 'edges': []})
    for node in graph.get('nodes', []):
        config = node.setdefault('config', {})
        for key, comodel in REF_KEYS.items():
            if config.get(key):
                config[key] = convert(comodel, config[key])
        Target = _rows_model(env, model, node)
        rows = (config.get('values') or []) if Target is not None else []
        for row in rows:
            field = Target._fields.get(row.get('field') or '')
            if not field or not field.relational or row.get('mode', 'value') != 'value' or not row.get('value'):
                continue
            if isinstance(row['value'], list):
                row['value'] = [convert(field.comodel_name, item) for item in row['value']]
            else:
                row['value'] = convert(field.comodel_name, row['value'])
        if node['type'] == 'create':
            # the id of a model differs in each database: the designer finds it from its name
            config.pop('model_id', None)
    return graph


def export_graph(env, model, graph):
    """ ``graph`` with its ids as references. """
    def to_ref(comodel, value):
        if not isinstance(value, int) or comodel not in env:
            return value
        record = env[comodel].sudo().browse(value).exists()
        if not record:
            return {REF: False, 'name': ''}
        return {REF: record.get_external_id().get(record.id) or False, 'name': record.display_name}
    return _walk(env, model, graph, to_ref)


def import_graph(env, model, graph):
    """ ``graph`` with its references as the ids of this database, and the
    names of those not found. """
    lost = []

    def to_id(comodel, value):
        if not isinstance(value, dict) or REF not in value:
            return value
        if comodel not in env:
            return False
        record = value[REF] and env.ref(value[REF], raise_if_not_found=False)
        if record and record._name == comodel:
            return record.id
        found = env[comodel].sudo().search([('display_name', '=', value.get('name'))], limit=2) if value.get('name') else []
        if len(found) == 1:
            return found.id
        lost.append(value.get('name') or value[REF] or '?')
        return False
    graph = _walk(env, model, graph, to_id)
    for node in graph.get('nodes', []):
        if node['type'] == 'create' and node['config'].get('model') in env:
            node['config']['model_id'] = env['ir.model']._get_id(node['config']['model'])
    return graph, lost
