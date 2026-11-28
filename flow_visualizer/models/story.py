# The story of a traced click, as a consultant tells it: the documents it
# touched (a quotation, a delivery, an invoice: any record with a chatter),
# each with its status and its lines, linked to the document that caused it.
import logging

from .tracer import is_noise

_logger = logging.getLogger(__name__)

DOCUMENTS_SHOWN = 30
ITEMS_SHOWN = 4
CHANGES_SHOWN = 4
QUANTITY_FIELDS = ('product_uom_qty', 'quantity', 'product_qty')
# the field that tells the kind of a document better than its model
TYPE_FIELDS = ('picking_type_id', 'move_type')
# chatter records: counted on their document, not listed
COUNTED_MODELS = {'mail.message': 'messages', 'mail.activity': 'activities'}


# the ORM methods a form calls, as a person names them
ORM_LABELS = {'write': 'Edit', 'web_save': 'Save', 'create': 'Create', 'unlink': 'Delete',
              'web_unlink': 'Delete', 'copy': 'Duplicate', 'rewind_apply': 'Go back'}


def action_label(method):
    """ ``action_confirm`` -> ``Confirm``: the button, as a person names it. """
    if method in ORM_LABELS:
        return ORM_LABELS[method]
    name = method
    for prefix in ('_action_', 'action_', 'button_'):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.replace('_', ' ').strip().capitalize() or method


class Story:

    def __init__(self, env, tracer):
        self.env = env
        self.tracer = tracer
        self._documents = {}

    def is_document(self, model):
        document = self._documents.get(model)
        if document is None:
            Model = self.env[model] if model in self.env else None
            document = bool(
                Model is not None and not is_noise(model) and not model.startswith('mail.')
                and not Model._transient and not Model._abstract and 'message_ids' in Model._fields
            )
            self._documents[model] = document
        return document

    def _events(self):
        """ What happened to each record, and the documents whose methods were running. """
        events = {}

        def visit(nodes, causes):
            for node in nodes:
                if node['kind'] == 'call':
                    inner = causes
                    if node['ids'] and self.is_document(node['model']):
                        inner = [*causes, (node['model'], node['ids'][0])]
                    visit(node.get('children', ()), inner)
                    continue
                changes = {change['id']: change['lines'] for change in node.get('changes', ())}
                for res_id in node['ids']:
                    event = events.get((node['model'], res_id))
                    if event is None:
                        event = events[node['model'], res_id] = {
                            'kind': node['kind'], 'changes': [], 'causes': causes,
                            'file': node.get('file'), 'line': node.get('line'), 'where': node.get('where'),
                        }
                    elif node['kind'] == 'unlink':
                        # made and dropped in the same click: nothing to tell
                        event['kind'] = 'gone' if event['kind'] == 'create' else 'unlink'
                    event['changes'] += changes.get(res_id, [])

        visit(self.tracer.root['children'], [])
        return {key: event for key, event in events.items() if event['kind'] != 'gone'}

    def _cause(self, causes, documents, key, entry):
        for cause in reversed(causes):
            if cause != key and cause in documents:
                return cause
        return entry if entry != key else None

    def _record_label(self, record):
        if 'product_id' in record._fields and record.product_id:
            label = record.product_id.display_name
            for name in QUANTITY_FIELDS:
                if name in record._fields and record[name]:
                    return f'{label} × {record[name]:g}'
            return label
        return record.display_name

    def _owners(self, model, ids, documents, created, causes_of, entry):
        """ The document each line belongs to: the one it points to, else the one that made it. """
        owners = {}
        fields = [
            field for field in self.env[model]._fields.values()
            if field.type == 'many2one' and field.store and self.is_document(field.comodel_name)
        ]
        for record in self.env[model].browse(ids).exists():
            linked = [(field.comodel_name, record[field.name].id) for field in fields if record[field.name]]
            linked = [key for key in linked if key in documents]
            owner = next((key for key in linked if key in created), None) or (linked[0] if linked else None)
            if owner:
                owners[record.id] = owner
        for res_id in ids:
            if res_id not in owners:
                owners[res_id] = self._cause(causes_of[model, res_id], documents, None, entry)
        return owners

    def build(self):
        env = self.env = self.env(su=True, context={**self.env.context, 'active_test': False})
        tracer = self.tracer
        events = self._events()
        entry = None
        if tracer.res_ids and self.is_document(tracer.model):
            entry = (tracer.model, tracer.res_ids[0])
        keys = [entry] if entry else []
        keys += [key for key in events if key != entry and self.is_document(key[0])]
        keys = keys[:DOCUMENTS_SHOWN]
        documents = set(keys)
        created = {key for key in keys if events.get(key, {}).get('kind') == 'create'}

        # the lines: every other record, put under its document
        line_ids = {}
        for (model, res_id), event in events.items():
            if not self.is_document(model) and not is_noise(model) and model not in COUNTED_MODELS:
                line_ids.setdefault(model, []).append(res_id)
        groups = {}
        causes_of = {key: event['causes'] for key, event in events.items()}
        for model, ids in line_ids.items():
            owners = self._owners(model, ids, documents, created, causes_of, entry)
            for res_id in ids:
                kind = events[model, res_id]['kind']
                group = groups.setdefault((owners[res_id], model, kind), {
                    'model': model, 'label': env[model]._description, 'kind': kind, 'ids': [],
                })
                group['ids'].append(res_id)
        for (_owner, model, kind), group in groups.items():
            group['count'] = len(group['ids'])
            if kind == 'unlink':
                group['items'] = [tracer.deleted_names.get((model, res_id), f'#{res_id}')
                                  for res_id in group['ids'][:ITEMS_SHOWN]]
            else:
                group['items'] = [self._record_label(record)
                                  for record in env[model].browse(group['ids'][:ITEMS_SHOWN]).exists()]

        # the documents
        cards = []
        for key in keys:
            model, res_id = key
            event = events.get(key, {'kind': 'write', 'changes': [], 'causes': []})
            card = {
                'key': f'{model},{res_id}', 'model': model, 'id': res_id,
                'model_label': env[model]._description,
                'kind': 'clicked' if key == entry else event['kind'],
                'parent': None,
                'name': tracer.deleted_names.get(key) or f'#{res_id}',
                'exists': False, 'type': '', 'partner': '', 'state': None, 'state_before': '', 'changes': [],
                'lines': [group for (owner, _model, _kind), group in groups.items() if owner == key],
                'messages': 0, 'activities': 0,
            }
            if event.get('file'):
                card.update(file=event['file'], line=event['line'], where=event.get('where'))
            parent = self._cause(event['causes'], documents, key, entry)
            card['parent'] = parent and f'{parent[0]},{parent[1]}'
            for label, before, after, *name in event['changes']:
                if name and name[0] == 'state':
                    card['state_before'] = card['state_before'] or before
                elif len(card['changes']) < CHANGES_SHOWN:
                    card['changes'].append([label, before, after])
            record = env[model].browse(res_id).exists()
            if record:
                card['exists'] = True
                card['name'] = record.display_name
                for name in TYPE_FIELDS:
                    if name in record._fields and record[name]:
                        field = record._fields[name]
                        card['type'] = (record[name].name or record[name].display_name if field.relational
                                        else dict(field._description_selection(env)).get(record[name], ''))
                        break
                if 'partner_id' in record._fields and record._fields['partner_id'].type == 'many2one':
                    card['partner'] = record.partner_id.display_name or ''
                if 'state' in record._fields and record._fields['state'].type == 'selection':
                    field = record._fields['state']
                    card['state'] = [record.state, dict(field._description_selection(env)).get(record.state, '')]
            cards.append(card)

        # the messages and activities, on the document they were posted on
        by_key = {(card['model'], card['id']): card for card in cards}
        counted = {model: [] for model in COUNTED_MODELS}
        for (model, res_id), event in events.items():
            if model in COUNTED_MODELS and event['kind'] == 'create':
                counted[model].append(res_id)
        for model, ids in counted.items():
            if not ids or model not in env:
                continue
            for record in env[model].browse(ids).exists():
                res_model = record.model if model == 'mail.message' else record.res_model
                card = by_key.get((res_model, record.res_id))
                if card:
                    card[COUNTED_MODELS[model]] += 1

        loose = [group for (owner, _model, _kind), group in groups.items() if owner is None]
        return {
            'action': action_label(tracer.method),
            'documents': cards,
            'loose': loose,
        }


def build_story(env, tracer):
    try:
        return Story(env, tracer).build()
    except Exception:  # noqa: BLE001 - the technical tree is still shown
        _logger.warning("Could not tell the story of %s.%s", tracer.model, tracer.method, exc_info=True)
        return None
