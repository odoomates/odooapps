""" The graph of a workflow, as the designer saves it::

    {
        'nodes': [{'id': 'n1', 'type': 'start', 'x': 80, 'y': 60, 'label': '', 'config': {...}}, ...],
        'edges': [{'id': 'e1', 'source': 'n1', 'port': 'out', 'target': 'n2'}, ...],
    }

A node has one exit per port of its type; an edge leaves a node by one of
them. A node with no edge on the port it leaves by ends the run.
"""
from dateutil.relativedelta import relativedelta

from odoo.tools import safe_eval

# the exits of each type of node, in the order the designer draws them
NODE_PORTS = {
    'start': ['out'],
    'condition': ['yes', 'no'],
    'wait': ['out'],
    'wait_until': ['done', 'timeout'],
    'approval': ['approved', 'rejected', 'timeout'],
    'update': ['out'],
    'create': ['out'],
    'email': ['out'],
    'activity': ['out'],
    'note': ['out'],
    'end': [],
}
# nodes that stop the run until something happens
WAIT_NODES = ('wait', 'wait_until', 'approval')
UNITS = {
    'minutes': relativedelta(minutes=1),
    'hours': relativedelta(hours=1),
    'days': relativedelta(days=1),
    'weeks': relativedelta(weeks=1),
    'months': relativedelta(months=1),
}
TRIGGERS = ('create', 'change', 'date', 'manual')
VALUE_MODES = ('value', 'field', 'today', 'clear')
# fields the designer does not list: technical, or chatter
HIDDEN_FIELD_PREFIXES = ('message_', 'activity_', 'website_message', '__', 'rating_')
HIDDEN_FIELD_TYPES = ('properties', 'properties_definition', 'json', 'binary', 'reference',
                      'many2one_reference')
# field types the update and create nodes can set
SETTABLE_TYPES = ('char', 'text', 'html', 'integer', 'float', 'monetary', 'boolean', 'selection',
                  'date', 'datetime', 'many2one', 'many2many')


def offset(amount, unit):
    return UNITS.get(unit, UNITS['days']) * int(amount or 0)


def graph_index(graph):
    """ The nodes of ``graph`` by id, and its edges by (source, port). """
    nodes = {node['id']: node for node in (graph or {}).get('nodes', [])}
    edges = {(edge['source'], edge['port']): edge['target'] for edge in (graph or {}).get('edges', [])}
    return nodes, edges


def eval_domain(env, domain):
    """ The domain the designer wrote, as a list. """
    if not domain or domain == '[]':
        return []
    if isinstance(domain, list):
        return domain
    return safe_eval.safe_eval(domain, {
        'uid': env.uid,
        'user': env.user,
        'datetime': safe_eval.datetime,
        'dateutil': safe_eval.dateutil,
        'time': safe_eval.time,
        'relativedelta': relativedelta,
        'context_today': safe_eval.datetime.date.today,
    })


def check_graph(env, model, graph):
    """ What keeps the workflow of ``model`` drawn as ``graph`` from running.

    :return: a list of ``{'node': id or False, 'level': 'error' or 'warning',
        'message': text}``; a workflow with errors cannot be published.
    """
    _ = env._
    issues = []

    def add(node, message, level='error'):
        issues.append({'node': node and node['id'], 'level': level, 'message': message})

    if not model or model not in env:
        add(None, _("Choose the model the workflow runs on."))
        return issues
    Model = env[model]
    nodes, edges = graph_index(graph)
    starts = [node for node in nodes.values() if node.get('type') == 'start']
    if len(starts) != 1:
        add(None, _("A workflow has exactly one Start."))

    for edge in (graph or {}).get('edges', []):
        source, target = nodes.get(edge['source']), nodes.get(edge['target'])
        if not source or not target:
            add(None, _("An arrow is not connected at both ends."))
        elif edge['port'] not in NODE_PORTS.get(source['type'], []):
            add(source, _("An arrow leaves this step by an exit it does not have."))
        elif target['type'] == 'start':
            add(target, _("No arrow can lead back to the Start."))

    for node in nodes.values():
        kind = node.get('type')
        if kind not in NODE_PORTS:
            add(node, _("Unknown step type %s.", kind))
            continue
        _check_node(env, Model, node, add)

    # what the Start cannot reach never runs
    if len(starts) == 1:
        reached, todo = set(), [starts[0]['id']]
        while todo:
            node_id = todo.pop()
            if node_id in reached or node_id not in nodes:
                continue
            reached.add(node_id)
            todo += [target for (source, __), target in edges.items() if source == node_id]
        for node in nodes.values():
            if node['id'] not in reached:
                add(node, _("No arrow leads to this step: it never runs."), 'warning')
        # a loop with no wait in it would run its steps over and over at once
        if _has_loop_without_wait(nodes, edges):
            add(None, _("A loop with no Wait or Approval in it would repeat at once: add a Wait to it."))
    return issues


def _has_loop_without_wait(nodes, edges):
    successors = {}
    for (source, __), target in edges.items():
        if nodes.get(source, {}).get('type') not in WAIT_NODES:
            successors.setdefault(source, []).append(target)
    state = {}

    def visit(node_id):
        state[node_id] = 'open'
        for target in successors.get(node_id, []):
            if nodes.get(target, {}).get('type') in WAIT_NODES:
                continue
            if state.get(target) == 'open' or (target not in state and visit(target)):
                return True
        state[node_id] = 'done'
        return False

    return any(node_id not in state and visit(node_id) for node_id in nodes)


def _check_domain(env, Model, node, domain, add):
    try:
        Model.search_count(eval_domain(env, domain), limit=1)
    except Exception:  # noqa: BLE001 any wrong condition, whatever the error
        add(node, env._("The condition is not valid."))


def _check_values(env, Model, node, rows, add, source_model=None):
    _ = env._
    if not rows:
        add(node, _("Add at least one field to set."))
    for row in rows or []:
        field = Model._fields.get(row.get('field') or '')
        if not field:
            add(node, _("Choose the field to set."))
            continue
        if field.type not in SETTABLE_TYPES or (field.compute and not field.inverse and field.readonly):
            add(node, _("The field %s cannot be set.", field.string))
        mode = row.get('mode', 'value')
        if mode not in VALUE_MODES:
            add(node, _("Choose how to set the field %s.", field.string))
        elif mode == 'field':
            source = (source_model or Model)._fields.get(row.get('source') or '')
            if not source:
                add(node, _("Choose the field to copy into %s.", field.string))
            elif field.relational and source.comodel_name != field.comodel_name:
                add(node, _("The field %(source)s holds no %(target)s.", source=source.string, target=field.string))
        elif mode == 'today' and field.type not in ('date', 'datetime'):
            add(node, _("Only a date can be set to today."))
        elif mode == 'value' and field.required and row.get('value') in (None, False, '', []):
            add(node, _("The field %s is required: give it a value.", field.string))


def _check_user(env, Model, node, config, add, what):
    """ The user a step is for: a chosen user, or the one of a field. """
    if config.get('assign', 'user') == 'field':
        field = Model._fields.get(config.get('user_field') or '')
        if not field or field.type != 'many2one' or field.comodel_name != 'res.users':
            add(node, env._("Choose the field that holds the %s.", what))
    elif not config.get('user_id') or not env['res.users'].browse(config['user_id']).exists():
        add(node, env._("Choose the %s.", what))


def _check_node(env, Model, node, add):
    _ = env._
    config = node.get('config') or {}
    kind = node['type']
    if kind == 'start':
        trigger = config.get('trigger')
        if trigger not in TRIGGERS:
            add(node, _("Choose what starts the workflow."))
        elif trigger == 'date':
            field = Model._fields.get(config.get('date_field') or '')
            if not field or field.type not in ('date', 'datetime') or not field.store:
                add(node, _("Choose the date field the workflow starts from."))
        for name in config.get('fields') or []:
            if name not in Model._fields:
                add(node, _("The watched field %s does not exist.", name))
        _check_domain(env, Model, node, config.get('domain'), add)
        if config.get('stop_domain'):
            _check_domain(env, Model, node, config['stop_domain'], add)
    elif kind in ('condition', 'wait_until'):
        if not config.get('domain') or config['domain'] == '[]':
            add(node, _("Set the condition."))
        else:
            _check_domain(env, Model, node, config['domain'], add)
    if kind == 'wait':
        if config.get('mode') == 'date':
            field = Model._fields.get(config.get('date_field') or '')
            if not field or field.type not in ('date', 'datetime'):
                add(node, _("Choose the date to wait for."))
        elif int(config.get('amount') or 0) <= 0:
            add(node, _("Set how long to wait."))
    if kind in ('wait_until', 'approval') and config.get('timeout') and int(config.get('amount') or 0) <= 0:
        add(node, _("Set the time limit."))
    if kind == 'approval':
        _check_user(env, Model, node, config, add, _("approver"))
        for name in config.get('lock_fields') or []:
            if name not in Model._fields:
                add(node, _("The blocked field %s does not exist.", name))
    elif kind == 'update':
        _check_values(env, Model, node, config.get('values'), add)
    elif kind == 'create':
        target = config.get('model')
        if not target or target not in env or env[target]._abstract or env[target]._transient:
            add(node, _("Choose the kind of record to create."))
        else:
            Target = env[target]
            _check_values(env, Target, node, config.get('values'), add, source_model=Model)
            link = config.get('link_field')
            if link and (link not in Target._fields or Target._fields[link].comodel_name != Model._name):
                add(node, _("The link field does not point to this record."))
    elif kind == 'email':
        template = env['mail.template'].browse(config.get('template_id') or []).exists()
        if not template:
            add(node, _("Choose the email template."))
        elif template.model != Model._name:
            add(node, _("The email template is not made for this model."))
    elif kind == 'activity':
        if 'activity_ids' not in Model._fields:
            add(node, _("This model has no activities."))
        if not env['mail.activity.type'].browse(config.get('activity_type_id') or []).exists():
            add(node, _("Choose the activity type."))
        _check_user(env, Model, node, config, add, _("person to assign"))
    elif kind == 'note':
        if 'message_ids' not in Model._fields:
            add(node, _("This model has no chatter."))
        if not (config.get('body') or '').strip():
            add(node, _("Write the message."))
