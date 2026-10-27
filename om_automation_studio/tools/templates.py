""" Workflow templates: generic patterns, such as an approval above a limit or
reminders once a date is passed, that a user applies to the model of their
choice. A pattern lists its settings as slots (a number field, a status and
its values, a user...), guesses them from the fields of the model, and builds
the chart from what the user chose. Presets give the exact settings of known
models (the discount of the lines of a quotation, the due date of an invoice).

A slot, as the template dialog receives it::

    {'name': 'number', 'type': 'field', 'label': 'Number', 'required': True,
     'options': [{'name': 'amount_total', 'string': 'Total', ...}], 'default': 'amount_total'}

Its value: a field name (``order_line.discount`` through lines), a list of
status values, a number, ``{'mode': 'field', 'field': 'user_id'}`` or
``{'mode': 'user', 'id': 2}`` for a user, a record id, a domain or a boolean.
"""
from itertools import pairwise

from .graph import HIDDEN_FIELD_PREFIXES, HIDDEN_FIELD_TYPES, eval_domain

COLUMN, ROW = 270, 130
NUMBER_TYPES = ('integer', 'float', 'monetary')
FILLABLE_TYPES = ('char', 'text', 'html', 'integer', 'float', 'monetary', 'date', 'datetime',
                  'many2one', 'many2many', 'selection')
# the fields tried first, by kind of slot
GUESSES = {
    'number': ['amount_total', 'expected_revenue', 'amount_untaxed', 'price_total', 'list_price'],
    'date': ['date_deadline', 'invoice_date_due', 'validity_date', 'date_planned', 'date_end', 'date'],
    'status': ['state', 'stage_id', 'status', 'won_status'],
    'user': ['user_id', 'invoice_user_id', 'responsible_id'],
}
# never guessed for a user: they are who touched the record last, not who owns it
NOT_OWNERS = ('write_uid',)


def n(node_id, kind, col, row, label, **config):
    return {'id': node_id, 'type': kind, 'x': 60 + col * COLUMN, 'y': 220 + row * ROW,
            'label': label, 'config': config}


def e(source, port, target):
    return {'id': f'{source}_{port}', 'source': source, 'port': port, 'target': target}


def chain(nodes):
    """ The edges that link ``nodes`` one after the other. """
    return [e(a['id'], 'out', b['id']) for a, b in pairwise(nodes)]


# ----------------------------------------------------------------------
# fields
# ----------------------------------------------------------------------

def _visible(env, name, field):
    return not (name == 'id' or name.startswith(HIDDEN_FIELD_PREFIXES) or field.type in HIDDEN_FIELD_TYPES
                or (field.groups and not env.user.has_groups(field.groups)))


def _fits(kind, name, field):
    if kind == 'number':
        return field.type in NUMBER_TYPES and field.store
    if kind == 'date':
        return field.type in ('date', 'datetime') and field.store
    if kind == 'status':
        return field.store and (field.type == 'selection'
                                or (field.type == 'many2one' and name.endswith('stage_id')))
    if kind == 'user':
        return field.type == 'many2one' and field.comodel_name == 'res.users'
    if kind == 'settable':
        return field.type in ('selection', 'boolean') and field.store and not (field.compute and not field.inverse)
    if kind == 'fillable':
        return field.type in FILLABLE_TYPES and field.store and not (field.compute and not field.inverse)
    return False


def _option(env, name, field, prefix=None):
    return {
        'name': f'{prefix[0]}.{name}' if prefix else name,
        'string': (f'{prefix[1]} > ' if prefix else '') + field._description_string(env),
        'type': field.type,
        'relation': getattr(field, 'comodel_name', None) or False,
        'selection': field._description_selection(env) if field.type == 'selection' else False,
    }


def field_options(env, Model, kind, paths=False):
    """ The fields of ``Model`` a slot of ``kind`` can take; with ``paths``,
    also those of its lines (``order_line.discount``). """
    options = [_option(env, name, field) for name, field in Model._fields.items()
               if _visible(env, name, field) and _fits(kind, name, field)]
    if paths:
        for name, field in Model._fields.items():
            if field.type != 'one2many' or not field.store or not _visible(env, name, field):
                continue
            Lines = env[field.comodel_name]
            line_name = field._description_string(env)
            options += [_option(env, line, line_field, (name, line_name))
                        for line, line_field in Lines._fields.items()
                        if _visible(env, line, line_field) and _fits(kind, line, line_field)]
    return sorted(options, key=lambda option: option['string'].lower())


def guess(options, kind, fallback=True):
    """ The likeliest of ``options``; with ``fallback``, the first one when
    no usual field is there. """
    names = [option['name'] for option in options if option['name'] not in NOT_OWNERS]
    for name in GUESSES.get(kind, []):
        if name in names:
            return name
    return names[0] if names and fallback else False


def field_label(env, Model, path, short=False):
    """ The label of ``path``, a field of ``Model`` or of its lines; with
    ``short``, of the field alone, as the steps of a chart show it. """
    labels = []
    for name in (path or '').split('.'):
        field = Model._fields[name]
        labels.append(field._description_string(env))
        if field.relational:
            Model = env[field.comodel_name]
    return labels[-1] if short else ' > '.join(labels)


# ----------------------------------------------------------------------
# slots
# ----------------------------------------------------------------------

def field_slot(env, Model, name, label, kind, required=True, paths=False, help=''):
    options = field_options(env, Model, kind, paths)
    return {'name': name, 'type': 'field', 'kind': kind, 'label': label, 'required': required,
            'help': help, 'options': options, 'default': guess(options, kind) if required or kind == 'status' else False}


def values_slot(name, label, of, required=True, help=''):
    """ Values of the status chosen in the slot ``of``. """
    return {'name': name, 'type': 'values', 'of': of, 'label': label, 'required': required,
            'help': help, 'default': []}


def value_slot(name, label, of, help=''):
    """ One value of the field chosen in the slot ``of``. """
    return {'name': name, 'type': 'value', 'of': of, 'label': label, 'required': False,
            'help': help, 'default': False}


def user_slot(env, Model, name, label, owner=True, help=''):
    """ A user, chosen or held by a field; ``owner`` guesses the field. """
    options = field_options(env, Model, 'user')
    # a record without its usual owner field is handled by a chosen user
    field = owner and guess(options, 'user', fallback=False)
    return {'name': name, 'type': 'user', 'label': label, 'required': True, 'help': help, 'options': options,
            'default': {'mode': 'field', 'field': field} if field else {'mode': 'user', 'id': env.uid}}


def number_slot(name, label, default, help='', days=False):
    return {'name': name, 'type': 'days' if days else 'number', 'label': label, 'required': True,
            'help': help, 'default': default}


def days_slot(name, label, default, help=''):
    return number_slot(name, label, default, help, days=True)


def template_slot(env, Model, name, label, help=''):
    templates = env['mail.template'].search([('model', '=', Model._name)], order='name')
    return {'name': name, 'type': 'template', 'label': label, 'required': False, 'help': help,
            'options': [{'id': template.id, 'name': template.name} for template in templates], 'default': False}


def domain_slot(name, label, help=''):
    return {'name': name, 'type': 'domain', 'label': label, 'required': False, 'help': help, 'default': '[]'}


def boolean_slot(name, label, default, help=''):
    return {'name': name, 'type': 'boolean', 'label': label, 'required': False, 'help': help, 'default': default}


def fields_slot(env, Model, name, label, help=''):
    return {'name': name, 'type': 'fields', 'label': label, 'required': True, 'help': help,
            'options': field_options(env, Model, 'fillable'), 'default': []}


def clean(env, slots, values):
    """ The values of ``slots``: those given when valid, else the defaults. """
    result = {}
    for slot in slots:
        value = values.get(slot['name'], slot['default'])
        kind = slot['type']
        if kind == 'field':
            if value not in [option['name'] for option in slot['options']]:
                value = False
        elif kind == 'fields':
            names = [option['name'] for option in slot['options']]
            value = [name for name in value or [] if name in names]
        elif kind == 'values':
            value = [item for item in value or [] if isinstance(item, (str, int)) and not isinstance(item, bool)]
        elif kind == 'value':
            value = value if isinstance(value, (str, int, bool)) else False
        elif kind == 'user':
            value = value if isinstance(value, dict) else slot['default']
            if value.get('mode') == 'field':
                if value.get('field') not in [option['name'] for option in slot['options']]:
                    value = {'mode': 'field', 'field': False}
            else:
                user = env['res.users'].browse(value.get('id') or []).exists() if isinstance(value.get('id'), int) else None
                value = {'mode': 'user', 'id': user.id if user else False}
        elif kind in ('number', 'days'):
            try:
                value = float(value) if kind == 'number' else max(0, int(value))
            except (TypeError, ValueError):
                value = slot['default']
        elif kind == 'template':
            value = value if value in [option['id'] for option in slot['options']] else False
        elif kind == 'domain':
            try:
                eval_domain(env, value or '[]')
            except Exception:  # noqa: BLE001 any wrong condition falls back to none
                value = '[]'
        elif kind == 'boolean':
            value = bool(value)
        result[slot['name']] = value
    return result


def missing(slots, values):
    """ The labels of the required slots left empty. """
    labels = []
    for slot in slots:
        value = values.get(slot['name'])
        if slot['type'] == 'user':
            value = value.get('field') if value.get('mode') == 'field' else value.get('id')
        if slot['required'] and (value is None or value is False or value in ('', [])):
            labels.append(slot['label'])
    return labels


# ----------------------------------------------------------------------
# what the nodes need
# ----------------------------------------------------------------------

def assign(user):
    """ The assignment config of an Activity or Approval for a user slot. """
    if user.get('mode') == 'field':
        return {'assign': 'field', 'user_field': user.get('field')}
    return {'assign': 'user', 'user_id': user.get('id')}


def activity(env, node_id, col, row, label, user, summary, kind='todo', days=0):
    type_id = env.ref(f'mail.mail_activity_data_{kind}').id
    return n(node_id, 'activity', col, row, label, activity_type_id=type_id, days=days,
             summary=summary, **assign(user))


def in_values(field, values):
    return [(field, 'in', values)] if field and values else []


def condition(env, value):
    return list(eval_domain(env, value or '[]'))


def watched(*paths):
    """ The fields a Start watches: none (any change) when one goes through lines. """
    if any(path and '.' in path for path in paths):
        return []
    return [path for path in paths if path]


# ----------------------------------------------------------------------
# patterns
# ----------------------------------------------------------------------

class Pattern:
    """ A generic workflow: ``slots`` for a model, ``build`` its chart. """
    key = icon = ''
    # the kinds of fields a model needs for the pattern
    needs = ()

    def name(self, env):
        raise NotImplementedError

    def description(self, env):
        raise NotImplementedError

    def slots(self, env, Model):
        raise NotImplementedError

    def build(self, env, Model, values):
        raise NotImplementedError

    def fits(self, env, Model):
        return all(field_options(env, Model, kind, paths=kind == 'number') for kind in self.needs)


class ApprovalLimit(Pattern):
    key, icon, needs = 'approval_limit', 'fa-thumbs-up', ('number',)

    def name(self, env):
        return env._("Approval above a limit")

    def description(self, env):
        return env._("A record above a limit (a discount, an amount, a quantity) waits for an approver, and "
                     "its status cannot change until the answer.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'number', _("Number"), 'number', paths=True,
                       help=_("A field of the record or of its lines.")),
            number_slot('limit', _("Approval when above"), 1000),
            field_slot(env, Model, 'status', _("Status"), 'status', required=False),
            values_slot('status_values', _("Only while the status is"), 'status', required=False),
            domain_slot('condition', _("Only for records that match")),
            user_slot(env, Model, 'approver', _("Approver"), owner=False),
            days_slot('days', _("Answer within (days)"), 2, _("0: no time limit.")),
            boolean_slot('block', _("Block the status until the answer"), True,
                         _("The record cannot be confirmed or sent while it waits.")),
            user_slot(env, Model, 'owner', _("Who revises a refused one")),
        ]

    def build(self, env, Model, values):
        _ = env._
        number, limit, status = values['number'], values['limit'], values['status']
        statuses = in_values(status, values['status_values'])
        above = [(number, '>', limit)]
        stop = ['!', *above]
        if statuses:
            stop = ['|', *stop, (status, 'not in', values['status_values'])]
        label = _("%(field)s above %(limit)s", field=field_label(env, Model, number, short=True), limit=f'{limit:g}')
        timeout = values['days'] > 0
        lock = values['block'] and bool(status)
        nodes = [
            n('start', 'start', 0, 0, label, trigger='change', fields=watched(number, status),
              domain=repr(statuses + above + condition(env, values['condition'])), becomes=True,
              policy='single', stop_domain=repr(stop)),
            n('approve', 'approval', 1, 0, _("Approve"), title=_("Approve {{ object.display_name }}"),
              note=label, timeout=timeout, amount=values['days'], unit='days', lock=lock, lock_mode='fields',
              lock_fields=[status] if lock else [], **assign(values['approver'])),
            n('ok', 'note', 2, -1, _("Log the approval"), body=_("Approved: %s.", label)),
            activity(env, 'revise', 2, 0, _("Revise it"), values['owner'],
                     _("Refused: revise {{ object.display_name }}")),
            n('end', 'end', 3, 0, ''),
        ]
        edges = [e('start', 'out', 'approve'), e('approve', 'approved', 'ok'), e('approve', 'rejected', 'revise'),
                 e('ok', 'out', 'end'), e('revise', 'out', 'end')]
        if timeout:
            nodes.append(activity(env, 'remind', 2, 1, _("Remind the approver"), values['approver'],
                                  _("{{ object.display_name }} waits for your answer")))
            edges += [e('approve', 'timeout', 'remind'), e('remind', 'out', 'end')]
        return {'nodes': nodes, 'edges': edges}


class FollowUp(Pattern):
    key, icon, needs = 'follow_up', 'fa-reply', ('status',)

    def name(self, env):
        return env._("Follow-up after a status")

    def description(self, env):
        return env._("Once a record reaches a status (a quotation sent, a request sent), a follow-up call "
                     "after some days, then a reminder email. A later status stops it.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'status', _("Status"), 'status'),
            values_slot('start_values', _("Starts when the status becomes"), 'status'),
            values_slot('stop_values', _("Stops when the status becomes"), 'status', required=False),
            domain_slot('condition', _("Only for records that match")),
            days_slot('days', _("Follow-up call after (days)"), 3),
            user_slot(env, Model, 'owner', _("Who follows up")),
            template_slot(env, Model, 'template', _("Then a reminder email"), _("Optional.")),
            days_slot('again', _("Email after (more days)"), 4),
        ]

    def build(self, env, Model, values):
        _ = env._
        status = values['status']
        nodes = [
            n('start', 'start', 0, 0, _("Status reached"), trigger='change', fields=[status],
              domain=repr(in_values(status, values['start_values']) + condition(env, values['condition'])),
              becomes=True, policy='single', stop_domain=repr(in_values(status, values['stop_values']))),
        ]
        if values['days']:
            nodes.append(n('wait', 'wait', len(nodes), 0, _("%s days later", values['days']), mode='duration',
                           amount=values['days'], unit='days'))
        nodes.append(activity(env, 'call', len(nodes), 0, _("Follow-up call"), values['owner'],
                              _("Follow up {{ object.display_name }}"), kind='call'))
        if values['template']:
            if values['again']:
                nodes.append(n('again', 'wait', len(nodes), 0, _("%s days later", values['again']),
                               mode='duration', amount=values['again'], unit='days'))
            nodes.append(n('mail', 'email', len(nodes), 0, _("Reminder email"), template_id=values['template']))
        nodes.append(n('end', 'end', len(nodes), 0, ''))
        return {'nodes': nodes, 'edges': chain(nodes)}


class Overdue(Pattern):
    key, icon, needs = 'overdue', 'fa-calendar-times-o', ('date',)

    def name(self, env):
        return env._("Reminders once a date is passed")

    def description(self, env):
        return env._("Some days after a date (a due date, an arrival, an expiry): reminder emails, then a "
                     "call. Done in the meantime: the reminders stop.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'date', _("Date"), 'date'),
            days_slot('days', _("Starts after (days)"), 1),
            domain_slot('condition', _("Only for records that match")),
            domain_slot('stop', _("Stops when the record matches")),
            template_slot(env, Model, 'template', _("Reminder email"), _("Optional.")),
            number_slot('reminders', _("Number of reminder emails"), 1),
            days_slot('interval', _("Days between the emails"), 7),
            user_slot(env, Model, 'owner', _("Then a call by")),
        ]

    def build(self, env, Model, values):
        _ = env._
        date = field_label(env, Model, values['date'])
        nodes = [
            n('start', 'start', 0, 0, _("%(date)s passed", date=date), trigger='date', date_field=values['date'],
              amount=values['days'], unit='days', direction='after',
              domain=repr(condition(env, values['condition'])), policy='single',
              stop_domain=repr(condition(env, values['stop']))),
        ]
        reminders = min(5, int(values['reminders'])) if values['template'] else 0
        for index in range(reminders):
            if index:
                nodes.append(n(f'wait{index}', 'wait', len(nodes), 0, _("%s days later", values['interval']),
                               mode='duration', amount=values['interval'], unit='days'))
            nodes.append(n(f'mail{index}', 'email', len(nodes), 0, _("Reminder %s", index + 1),
                           template_id=values['template']))
        if reminders:
            nodes.append(n('wait_call', 'wait', len(nodes), 0, _("%s days later", values['interval']),
                           mode='duration', amount=values['interval'], unit='days'))
        nodes.append(activity(env, 'call', len(nodes), 0, _("Call"), values['owner'],
                              _("%(date)s of {{ object.display_name }} is passed", date=date), kind='call'))
        nodes.append(n('end', 'end', len(nodes), 0, ''))
        return {'nodes': nodes, 'edges': chain(nodes)}


class BeforeDate(Pattern):
    key, icon, needs = 'before_date', 'fa-calendar', ('date',)

    def name(self, env):
        return env._("Reminder before a date")

    def description(self, env):
        return env._("Some days before a date (a deadline, an expiry, a renewal): an activity for whoever "
                     "handles the record.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'date', _("Date"), 'date'),
            days_slot('days', _("Days before"), 3),
            domain_slot('condition', _("Only for records that match")),
            user_slot(env, Model, 'owner', _("Who is reminded")),
        ]

    def build(self, env, Model, values):
        _ = env._
        date = field_label(env, Model, values['date'])
        nodes = [
            n('start', 'start', 0, 0, _("%(days)s days before %(date)s", days=values['days'], date=date),
              trigger='date', date_field=values['date'], amount=values['days'], unit='days', direction='before',
              domain=repr(condition(env, values['condition'])), policy='single'),
            activity(env, 'remind', 1, 0, _("Reminder"), values['owner'],
                     _("%(date)s of {{ object.display_name }} in %(days)s days", date=date, days=values['days'])),
            n('end', 'end', 2, 0, ''),
        ]
        return {'nodes': nodes, 'edges': chain(nodes)}


class Stuck(Pattern):
    key, icon, needs = 'stuck', 'fa-hourglass-start', ('status',)

    def name(self, env):
        return env._("Stuck in a status")

    def description(self, env):
        return env._("A record stays in a status for some days: whoever handles it is reminded, then a "
                     "manager. Moving on stops it.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'status', _("Status"), 'status'),
            values_slot('values', _("Stuck in"), 'status'),
            domain_slot('condition', _("Only for records that match")),
            days_slot('days', _("Reminder after (days)"), 7),
            user_slot(env, Model, 'owner', _("Who is reminded")),
            days_slot('escalate', _("Then the manager after (more days)"), 3, _("0: no manager.")),
            user_slot(env, Model, 'manager', _("Manager"), owner=False),
        ]

    def build(self, env, Model, values):
        _ = env._
        status, stuck = values['status'], values['values']
        nodes = [
            n('start', 'start', 0, 0, _("Status reached"), trigger='change', fields=[status],
              domain=repr(in_values(status, stuck) + condition(env, values['condition'])), becomes=True,
              policy='single', stop_domain=repr([(status, 'not in', stuck)] if stuck else [])),
            n('wait', 'wait', 1, 0, _("%s days later", values['days']), mode='duration',
              amount=max(1, values['days']), unit='days'),
            activity(env, 'remind', 2, 0, _("Remind"), values['owner'],
                     _("{{ object.display_name }} has not moved for %s days", values['days'])),
        ]
        if values['escalate']:
            nodes += [
                n('wait_manager', 'wait', 3, 0, _("%s days later", values['escalate']), mode='duration',
                  amount=values['escalate'], unit='days'),
                activity(env, 'escalate', 4, 0, _("Tell the manager"), values['manager'],
                         _("{{ object.display_name }} is still stuck")),
            ]
        nodes.append(n('end', 'end', len(nodes), 0, ''))
        return {'nodes': nodes, 'edges': chain(nodes)}


class NewRecord(Pattern):
    key, icon, needs = 'new_record', 'fa-user-plus', ('user',)

    def name(self, env):
        return env._("New record response")

    def description(self, env):
        return env._("A new record gets a call from whoever handles it; with nobody yet, a manager is asked "
                     "to assign someone.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'owner', _("Who handles it"), 'user'),
            domain_slot('condition', _("Only for records that match")),
            days_slot('days', _("Call due in (days)"), 0),
            user_slot(env, Model, 'manager', _("Without anybody, ask"), owner=False),
        ]

    def build(self, env, Model, values):
        _ = env._
        owner = values['owner']
        nodes = [
            n('start', 'start', 0, 0, _("Created"), trigger='create', domain=repr(condition(env, values['condition'])),
              policy='once'),
            n('owner', 'condition', 1, 0, _("Somebody handles it?"), domain=repr([(owner, '!=', False)])),
            activity(env, 'call', 2, -1, _("Call"), {'mode': 'field', 'field': owner},
                     _("Call about {{ object.display_name }}"), kind='call', days=values['days']),
            activity(env, 'assign', 2, 1, _("Assign somebody"), values['manager'],
                     _("Assign somebody to {{ object.display_name }}")),
            n('end', 'end', 3, 0, ''),
        ]
        edges = [e('start', 'out', 'owner'), e('owner', 'yes', 'call'), e('owner', 'no', 'assign'),
                 e('call', 'out', 'end'), e('assign', 'out', 'end')]
        return {'nodes': nodes, 'edges': edges}


class BigValue(Pattern):
    key, icon, needs = 'big_value', 'fa-star', ('number',)

    def name(self, env):
        return env._("Big value alert")

    def description(self, env):
        return env._("A record reaches a value (an amount, a revenue): mark it, for instance with a "
                     "priority, and somebody reviews it.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'number', _("Number"), 'number', paths=True),
            number_slot('limit', _("At least"), 10000),
            domain_slot('condition', _("Only for records that match")),
            field_slot(env, Model, 'set_field', _("Then set"), 'settable', required=False, help=_("Optional.")),
            value_slot('set_value', _("To"), 'set_field'),
            user_slot(env, Model, 'reviewer', _("Who reviews it"), owner=False),
        ]

    def build(self, env, Model, values):
        _ = env._
        number = values['number']
        label = _("%(field)s %(limit)s or more", field=field_label(env, Model, number, short=True),
                  limit=f"{values['limit']:g}")
        nodes = [
            n('start', 'start', 0, 0, label, trigger='change', fields=watched(number),
              domain=repr([(number, '>=', values['limit'])] + condition(env, values['condition'])), becomes=True,
              policy='once'),
        ]
        field = values['set_field']
        if field and (values['set_value'] not in (False, None, '') or Model._fields[field].type == 'boolean'):
            value = bool(values['set_value']) if Model._fields[field].type == 'boolean' else values['set_value']
            nodes.append(n('mark', 'update', 1, 0, _("Set %s", field_label(env, Model, field)),
                           values=[{'field': field, 'mode': 'value', 'value': value}]))
        nodes.append(activity(env, 'review', len(nodes), 0, _("Review"), values['reviewer'],
                              _("Review {{ object.display_name }}: %s", label)))
        nodes.append(n('end', 'end', len(nodes), 0, ''))
        return {'nodes': nodes, 'edges': chain(nodes)}


class MissingInfo(Pattern):
    key, icon, needs = 'missing_info', 'fa-pencil-square-o', ('fillable',)

    def name(self, env):
        return env._("Missing information")

    def description(self, env):
        return env._("Some days after a record is created, fields still empty (an email, a phone): whoever "
                     "handles it completes them.")

    def slots(self, env, Model):
        _ = env._
        return [
            fields_slot(env, Model, 'fields', _("Fields to fill")),
            days_slot('days', _("Check after (days)"), 2),
            domain_slot('condition', _("Only for records that match")),
            user_slot(env, Model, 'owner', _("Who completes them")),
        ]

    def build(self, env, Model, values):
        _ = env._
        names = values['fields']
        empty = []
        for index, name in enumerate(names):
            if index:
                empty.insert(0, '|')
            empty.append((name, '=', False))
        labels = ', '.join(field_label(env, Model, name) for name in names)
        nodes = [
            n('start', 'start', 0, 0, _("Created"), trigger='create', domain=repr(condition(env, values['condition'])),
              policy='once'),
        ]
        if values['days']:
            nodes.append(n('wait', 'wait', 1, 0, _("%s days later", values['days']), mode='duration',
                           amount=values['days'], unit='days'))
        check = n('empty', 'condition', len(nodes), 0, _("Still missing?"), domain=repr(empty))
        complete = activity(env, 'complete', len(nodes) + 1, -1, _("Complete it"), values['owner'],
                            _("Complete {{ object.display_name }}: %s", labels))
        end = n('end', 'end', len(nodes) + 2, 0, '')
        edges = chain([*nodes, check]) + [e('empty', 'yes', 'complete'), e('empty', 'no', 'end'),
                                          e('complete', 'out', 'end')]
        return {'nodes': [*nodes, check, complete, end], 'edges': edges}


class AfterDone(Pattern):
    key, icon, needs = 'after_done', 'fa-check-circle', ('status',)

    def name(self, env):
        return env._("After completion")

    def description(self, env):
        return env._("A record is done (won, confirmed, paid): logged in the chatter, then a thank-you or "
                     "a review request some days later.")

    def slots(self, env, Model):
        _ = env._
        return [
            field_slot(env, Model, 'status', _("Status"), 'status'),
            values_slot('values', _("When the status becomes"), 'status'),
            domain_slot('condition', _("Only for records that match")),
            days_slot('days', _("Follow up after (days)"), 7),
            template_slot(env, Model, 'template', _("By email"), _("Optional: else, an activity.")),
            user_slot(env, Model, 'owner', _("Who follows up")),
        ]

    def build(self, env, Model, values):
        _ = env._
        status = values['status']
        nodes = [
            n('start', 'start', 0, 0, _("Done"), trigger='change', fields=[status],
              domain=repr(in_values(status, values['values']) + condition(env, values['condition'])),
              becomes=True, policy='once'),
            n('log', 'note', 1, 0, _("Log it"), body=_("Done: {{ object.display_name }}.")),
        ]
        if values['days']:
            nodes.append(n('wait', 'wait', 2, 0, _("%s days later", values['days']), mode='duration',
                           amount=values['days'], unit='days'))
        if values['template']:
            nodes.append(n('mail', 'email', len(nodes), 0, _("Email"), template_id=values['template']))
        else:
            nodes.append(activity(env, 'thanks', len(nodes), 0, _("Thank-you"), values['owner'],
                                  _("Thank the customer of {{ object.display_name }}"), kind='call'))
        nodes.append(n('end', 'end', len(nodes), 0, ''))
        return {'nodes': nodes, 'edges': chain(nodes)}


PATTERNS = {pattern.key: pattern for pattern in (
    ApprovalLimit(), FollowUp(), Overdue(), BeforeDate(), Stuck(), NewRecord(), BigValue(), MissingInfo(),
    AfterDone(),
)}


# ----------------------------------------------------------------------
# presets: the settings of known models, and the demo workflows
# ----------------------------------------------------------------------

def _template(env, xmlid):
    template = env.ref(xmlid, raise_if_not_found=False)
    return template.id if template else False


def _receipt(env):
    """ Not fully received: known with Inventory only. """
    if 'receipt_status' not in env['purchase.order']._fields:
        return {'condition': repr([('state', '=', 'purchase')])}
    return {'condition': repr([('state', '=', 'purchase'), ('receipt_status', '!=', 'full')]),
            'stop': repr([('receipt_status', '=', 'full')])}


UNPAID = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ['not_paid', 'partial'])]
OPEN_LEAD = [('won_status', '=', 'pending')]

# (pattern, model): app, name, values (or a function of env giving them)
PRESETS = {
    ('approval_limit', 'sale.order'): ('sale', "Sales: Discount Approval", {
        'number': 'order_line.discount', 'limit': 20, 'status': 'state', 'status_values': ['draft', 'sent']}),
    ('follow_up', 'sale.order'): ('sale', "Sales: Quotation Follow-up", lambda env: {
        'status': 'state', 'start_values': ['sent'], 'stop_values': ['sale', 'cancel'], 'days': 3,
        'template': _template(env, 'sale.email_template_edi_sale'), 'again': 4}),
    ('after_done', 'sale.order'): ('sale', "Sales: Order Thank-you", {
        'status': 'state', 'values': ['sale'], 'condition': repr([('amount_total', '>=', 1500)]), 'days': 1}),
    ('overdue', 'sale.order'): ('sale', "Sales: Expired Quotation", {
        'date': 'validity_date', 'days': 1, 'condition': repr([('state', 'in', ['draft', 'sent'])]),
        'stop': repr([('state', 'in', ['sale', 'cancel'])])}),
    ('new_record', 'crm.lead'): ('crm', "CRM: New Lead Response", {'owner': 'user_id'}),
    ('big_value', 'crm.lead'): ('crm', "CRM: Big Opportunity", {
        'number': 'expected_revenue', 'limit': 10000, 'set_field': 'priority', 'set_value': '3',
        'condition': repr([('type', '=', 'opportunity'), *OPEN_LEAD])}),
    ('overdue', 'crm.lead'): ('crm', "CRM: Closing Date Passed", {
        'date': 'date_deadline', 'days': 1, 'condition': repr(OPEN_LEAD),
        'stop': repr([('won_status', '!=', 'pending')])}),
    ('after_done', 'crm.lead'): ('crm', "CRM: Won Opportunity", {'status': 'won_status', 'values': ['won']}),
    ('approval_limit', 'purchase.order'): ('purchase', "Purchase: Big Order Approval", {
        'number': 'amount_total', 'limit': 5000, 'status': 'state', 'status_values': ['draft', 'sent']}),
    ('follow_up', 'purchase.order'): ('purchase', "Purchase: RFQ Follow-up", {
        'status': 'state', 'start_values': ['sent'], 'stop_values': ['purchase', 'cancel'], 'days': 3}),
    ('overdue', 'purchase.order'): ('purchase', "Purchase: Late Receipt", lambda env: {
        'date': 'date_planned', 'days': 1, **_receipt(env)}),
    ('overdue', 'account.move'): ('account', "Invoices: Overdue Reminders", lambda env: {
        'date': 'invoice_date_due', 'days': 3, 'condition': repr(UNPAID),
        'stop': repr([('payment_state', 'in', ['paid', 'in_payment', 'reversed'])]),
        'template': _template(env, 'account.email_template_edi_invoice'), 'reminders': 2, 'interval': 12,
        'owner': {'mode': 'field', 'field': 'invoice_user_id'}}),
    ('approval_limit', 'account.move'): ('account', "Vendor Bills: Approval", {
        'number': 'amount_total', 'limit': 5000, 'status': 'state', 'status_values': ['draft'],
        'condition': repr([('move_type', '=', 'in_invoice')]),
        'owner': {'mode': 'field', 'field': 'invoice_user_id'}}),
    ('after_done', 'account.move'): ('account', "Invoices: Paid", {
        'status': 'payment_state', 'values': ['paid', 'in_payment'],
        'condition': repr([('move_type', '=', 'out_invoice')]), 'days': 0,
        'owner': {'mode': 'field', 'field': 'invoice_user_id'}}),
    ('missing_info', 'res.partner'): ('base', "Contacts: Missing Email or Phone", {
        'fields': ['email', 'phone'], 'days': 2, 'owner': {'mode': 'field', 'field': 'user_id'}}),
}


def preset_values(env, key, model):
    preset = PRESETS.get((key, model))
    if not preset:
        return {}
    values = preset[2]
    return values(env) if callable(values) else dict(values)
