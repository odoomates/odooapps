# The recorder of one traced client call: every record created, edited or
# deleted, hung under the chain of business methods that led to it (a button
# method, then the methods it called), read from the Python stack at the time.
import logging
import os
import re
import sys
import time
from contextvars import ContextVar

import odoo
from odoo.exceptions import UserError
from odoo.models import BaseModel

from .code_link import short_path

_logger = logging.getLogger(__name__)

# the tracer of the call being run, None when nothing is traced
CURRENT = ContextVar('flow_visualizer_tracer', default=None)

# Odoo's own code (ORM, HTTP, services) is plumbing; the addons are the business,
# base included. This module's own frames are never shown.
CORE_DIRS = tuple(os.path.join(path, '') for path in odoo.__path__)
CORE_ADDONS_DIRS = tuple(os.path.join(path, 'addons', '') for path in odoo.__path__)
OWN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '')

# the methods that are the events themselves, not their causes
EVENT_METHODS = frozenset({'create', 'write', 'unlink'})
# chatter and tracking plumbing: what they create hangs under their caller
PLUMBING_PREFIXES = ('_message_', '_track_', 'message_post', '_notify', '_mail_')
SKIPPED_FIELDS = frozenset({'write_date', 'write_uid', 'create_date', 'create_uid', '__last_update'})
# what must never be kept in a trace: passwords, keys and tokens, and the system parameters that hold them
SENSITIVE_FIELD = re.compile(r'pass(word|wd|phrase)?$|secret|token|api_?key|private_key|credential', re.IGNORECASE)
SENSITIVE_MODELS = frozenset({'ir.config_parameter'})
HIDDEN_VALUE = '(hidden)'
# records nobody asked for: shown only when the technical ones are
NOISE_MODELS = frozenset({
    'mail.followers', 'mail.tracking.value', 'mail.notification', 'mail.message.reaction',
    'bus.bus', 'bus.presence', 'res.users.log', 'res.users.settings', 'stock.reference',
    'stock.quant',
})
NOISE_PREFIXES = ('ir.', 'base_import.', 'mail.alias')

MAX_NODES = 3000
RECORDS_SHOWN = 20
RECORDS_KEPT = 200
CHANGED_RECORDS_SHOWN = 10
VALUE_LENGTH = 120

# code object -> whether its frames are business methods
_business_codes = {}


def is_business_code(code):
    business = _business_codes.get(code)
    if business is None:
        filename = code.co_filename
        business = (
            code.co_argcount > 0 and code.co_varnames[0] == 'self'
            and code.co_name not in EVENT_METHODS and not code.co_name.startswith(('__', *PLUMBING_PREFIXES))
            and not filename.startswith(OWN_DIR)
            and (filename.startswith(CORE_ADDONS_DIRS) or not filename.startswith(CORE_DIRS))
        )
        _business_codes[code] = business
    return business


def is_noise(model_name):
    return model_name in NOISE_MODELS or model_name.startswith(NOISE_PREFIXES)


def is_sensitive(model, name):
    return model in SENSITIVE_MODELS or bool(SENSITIVE_FIELD.search(name))


def value_text(record, field):
    """ A field's value of one record, as a person reads it. """
    if is_sensitive(record._name, field.name):
        return HIDDEN_VALUE
    value = record[field.name]
    if field.type == 'binary':
        return '(file)' if value else ''
    if field.type in ('many2one', 'many2one_reference') and hasattr(value, 'display_name'):
        return value.display_name or ''
    if field.relational:
        names = value.mapped('display_name')
        return ', '.join(names[:5]) + (f' (+{len(names) - 5})' if len(names) > 5 else '')
    if field.type == 'selection':
        return dict(field._description_selection(record.env)).get(value, value or '')
    if value is False and field.type != 'boolean':
        return ''
    text = str(value)
    return text if len(text) <= VALUE_LENGTH else text[:VALUE_LENGTH] + '…'


class Tracer:

    def __init__(self, env, model, method, args):
        self.cr = env.cr
        self.model = model
        self.method = method
        self.res_ids = [i for i in (args[0] if args and isinstance(args[0], list) else []) if isinstance(i, int)]
        self.started = time.perf_counter()
        self.queries = env.cr.sql_log_count
        self.root = {'children': []}
        self.count = 0
        self.truncated = False
        # the node of each running business method, by the id of its frame;
        # the frames are kept so that their ids are not given to others
        self.nodes = {}
        self.frames = []
        # the names of the deleted records, read before they go
        self.deleted_names = {}
        self.site = None
        self.trace_id = None
        self.failed = False
        self.story = None

    #
    # the tree
    #

    def _node(self, kind, records, **values):
        self.count += 1
        ids = [i for i in records._ids if isinstance(i, int)]
        return {
            'id': self.count, 'kind': kind, 'model': records._name, 'label': records._description,
            'ids': ids[:RECORDS_KEPT], 'total': len(ids), 'noise': is_noise(records._name),
            **values,
        }

    def _parent(self):
        """ The node of the innermost business method running, made with its callers when new. """
        chain = []
        frame = sys._getframe(1)
        while frame is not None:
            if is_business_code(frame.f_code):
                records = frame.f_locals.get('self')
                if isinstance(records, BaseModel):
                    chain.append((frame, records))
            frame = frame.f_back
        parent = self.root
        for frame, records in reversed(chain):
            node = self.nodes.get(id(frame))
            if node is None:
                name = frame.f_code.co_name
                if parent.get('method') == name and parent['model'] == records._name:
                    # an override calling super(): one method to the reader
                    node = parent
                else:
                    node = self._node('call', records, method=name, children=[],
                                      file=frame.f_code.co_filename, line=frame.f_code.co_firstlineno)
                    parent['children'].append(node)
                self.nodes[id(frame)] = node
                self.frames.append(frame)
            parent = node
        # the line of business code that made the event
        self.site = (chain[0][0].f_code.co_filename, chain[0][0].f_lineno) if chain else None
        return parent

    def _event(self, kind, records, changes=None, fields=None):
        if self.count >= MAX_NODES:
            self.truncated = True
            return
        parent = self._parent()
        siblings = parent['children']
        last = siblings[-1] if siblings else None
        # the same change on records of one model, one after the other: one line
        if last and last['kind'] == kind and last['model'] == records._name and last.get('fields') == fields:
            known = set(last['ids'])
            new_ids = [i for i in records._ids if isinstance(i, int) and i not in known]
            last['total'] += len(new_ids)
            last['ids'] += new_ids[:max(0, RECORDS_KEPT - len(last['ids']))]
            if changes:
                last['changes'] += changes[:max(0, CHANGED_RECORDS_SHOWN - len(last['changes']))]
            return
        node = self._node(kind, records)
        if self.site:
            node['file'], node['line'] = self.site
        if fields is not None:
            node['fields'] = fields
            node['changes'] = changes or []
        siblings.append(node)

    #
    # the events, called by the ORM methods of every model
    #

    def created(self, records):
        self._event('create', records)

    def written_fields(self, records, vals):
        return [
            name for name in vals
            if name in records._fields and name not in SKIPPED_FIELDS and records._fields[name].store
            and records._fields[name].type not in ('one2many', 'binary')
        ]

    def values(self, records, names):
        if not names:
            return {}
        records = records[:CHANGED_RECORDS_SHOWN].sudo().with_context(active_test=False, prefetch_fields=False)
        try:
            return {
                record.id: {name: value_text(record, record._fields[name]) for name in names}
                for record in records if isinstance(record.id, int)
            }
        except Exception:  # noqa: BLE001 - a value the tracer cannot read never stops the write
            _logger.debug("Could not read the values of %s", records, exc_info=True)
            return {}

    def written(self, records, names, before):
        after = self.values(records, names)
        labels = {name: records._fields[name]._description_string(records.env) for name in names}
        changes = []
        for res_id, values in after.items():
            lines = [
                [labels[name], before.get(res_id, {}).get(name, ''), value, name]
                for name, value in values.items() if before.get(res_id, {}).get(name) != value
            ]
            if lines:
                changes.append({'id': res_id, 'lines': lines})
        self._event('write', records, changes=changes, fields=sorted(names))

    def deleting(self, records):
        try:
            for record in records[:RECORDS_SHOWN].sudo().with_context(active_test=False):
                self.deleted_names[(record._name, record.id)] = record.display_name
        except Exception:  # noqa: BLE001
            _logger.debug("Could not read the names of %s", records, exc_info=True)
        self._event('unlink', records)

    #
    # the end of the call
    #

    def _walk(self, node):
        for child in node.get('children', ()):
            yield child
            yield from self._walk(child)

    def _resolve_names(self, env):
        """ Name the records shown, and tell those that still exist. """
        wanted = {}
        for node in self._walk(self.root):
            if node['kind'] != 'unlink':
                wanted.setdefault(node['model'], set()).update(node['ids'][:RECORDS_SHOWN])
        names = {}
        for model, ids in wanted.items():
            try:
                records = env[model].sudo().with_context(active_test=False).browse(ids).exists()
                names.update({(model, record.id): record.display_name for record in records})
            except Exception:  # noqa: BLE001
                _logger.debug("Could not name the records of %s", model, exc_info=True)
        return names

    def finish(self, env, error):
        """ Save the trace on a cursor of its own: it outlives a call that fails.

        Returns the error of the final flush of the call, made here before
        reading the names: the caller raises it, as the commit would have. """
        self.frames.clear()
        self.nodes.clear()
        flush_error = None
        names = {}
        if error is None:
            try:
                env.flush_all()
            except Exception as exc:  # noqa: BLE001 - raised again by the caller
                flush_error = exc
        failure = error or flush_error
        for node in self._walk(self.root):
            if node.get('file'):
                node['where'] = f"{short_path(node['file'])}:{node['line']}"
        story = None
        if failure is None:
            names = self._resolve_names(env)
            # imported here: the story module imports this one
            from .story import build_story  # noqa: PLC0415
            story = self.story = build_story(env, self)
        if not self.count and failure is None:
            return None
        for node in self._walk(self.root):
            records = []
            for res_id in node['ids'][:RECORDS_SHOWN]:
                key = (node['model'], res_id)
                if node['kind'] == 'unlink':
                    records.append([res_id, self.deleted_names.get(key) or f'#{res_id}', False])
                else:
                    records.append([res_id, names.get(key) or f'#{res_id}', key in names])
            node['records'] = records
        if isinstance(failure, UserError):
            message = failure.args[0] if failure.args else str(failure)
        else:
            message = failure and f'{type(failure).__name__}: {failure}'
        self.failed = bool(failure)
        self.trace_id = env['flow.visualizer.trace']._flow_save(env.registry, {
            'user_id': env.uid,
            'name': f'{self.model}.{self.method}',
            'model': self.model,
            'method': self.method,
            'res_ids': self.res_ids[:RECORDS_KEPT],
            'state': 'failed' if failure else 'done',
            'error': message or False,
            'duration': (time.perf_counter() - self.started) * 1000,
            'query_count': self.cr.sql_log_count - self.queries,
            'record_count': sum(node['total'] for node in self._walk(self.root) if node['kind'] != 'call'),
            'truncated': self.truncated,
            'tree': self.root['children'],
            'story': story,
        })
        return flush_error
