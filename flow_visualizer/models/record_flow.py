# The flow of an existing record: the documents linked to it (a quotation, its
# deliveries, its invoices, their payments), found through their relational
# fields, and a timeline of what happened to them: created, their key dates and
# the status changes their chatter logged.
import html
import logging
import re
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

from .tracer import is_noise

_logger = logging.getLogger(__name__)

DEPTH = 3
DOCUMENTS_SHOWN = 25
LINKS_PER_FIELD = 10
# the status-like fields whose changes make the timeline
TIMELINE_FIELDS = ('state', 'payment_state', 'stage_id')
# the dates that tell a document's story better than its creation
MILESTONES = {
    'sale.order': [('date_order', 'Ordered')],
    'purchase.order': [('date_approve', 'Confirmed'), ('date_planned', 'Expected')],
    'stock.picking': [('scheduled_date', 'Scheduled'), ('date_done', 'Done')],
    'account.move': [('invoice_date', 'Invoice date'), ('invoice_date_due', 'Due')],
    'account.payment': [('date', 'Paid')],
    'mrp.production': [('date_start', 'Started'), ('date_finished', 'Finished')],
}
# the milestones that are plans, not facts: not put on the timeline
PLANNED = {('purchase.order', 'date_planned'), ('stock.picking', 'scheduled_date'), ('account.move', 'invoice_date_due')}
TYPE_FIELDS = ('picking_type_id', 'move_type')
# fields that suggest records rather than link them (duplicates, similar ones)
SUGGESTION_FIELD = re.compile(r'duplicat|similar|suggest|candidate')
AMOUNT_FIELDS = ('amount_total', 'amount')
# "Old → <b>New</b> <i>(Field)</i>": the tracking line a chatter message holds
TRACKING_LINE = re.compile(
    r'(?:<em>[^<]*</em>)?(?P<old>[^<>]*?)\s*→\s*<b>(?P<new>.*?)</b>\s*<i>\((?P<label>.*?)\)</i>', re.S)


def text(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


class FlowVisualizerRecord(models.AbstractModel):
    _name = 'flow.visualizer.record'
    _description = 'Flow Visualizer: the flow of a record'

    @api.model
    def _flow_is_document(self, model):
        """ A transactional document: it has a chatter and a status. """
        if model not in self.env or is_noise(model) or model.startswith(('mail.', 'res.')):
            return False
        Model = self.env[model]
        if Model._transient or Model._abstract or 'message_ids' not in Model._fields:
            return False
        state = Model._fields.get('state')
        stage = Model._fields.get('stage_id')
        return bool((state and state.type == 'selection') or (stage and stage.type == 'many2one'))

    @api.model
    def _flow_skip(self, record):
        """ Linked documents nobody follows: the accounting entry behind a payment. """
        return record._name == 'account.move' and record.move_type == 'entry'

    @api.model
    def _flow_links(self, start):
        """ The documents linked to ``start``, a few steps away, that the user can read. """
        documents = {(start._name, start.id): {'record': start, 'depth': 0, 'parent': None, 'via': ''}}
        links = []
        frontier = [start]
        for depth in range(1, DEPTH + 1):
            next_frontier = []
            for record in frontier:
                for field in record._fields.values():
                    if field.type not in ('many2one', 'one2many', 'many2many'):
                        continue
                    if not self._flow_is_document(field.comodel_name):
                        continue
                    if (not field.store and not field.compute) or SUGGESTION_FIELD.search(field.name):
                        continue
                    try:
                        linked = record[field.name][:LINKS_PER_FIELD]._filtered_access('read')
                    except Exception:  # noqa: BLE001 - a field that cannot be read links nothing
                        _logger.debug("Could not follow %s.%s", record._name, field.name, exc_info=True)
                        continue
                    for other in linked:
                        if self._flow_skip(other):
                            continue
                        key = (other._name, other.id)
                        source = (record._name, record.id)
                        if key == source:
                            continue
                        pair = {source, key}
                        if not any({link[0], link[1]} == pair for link in links):
                            links.append((source, key, field._description_string(self.env)))
                        if key not in documents and len(documents) < DOCUMENTS_SHOWN:
                            documents[key] = {
                                'record': other, 'depth': depth, 'parent': source,
                                'via': field._description_string(self.env),
                            }
                            next_frontier.append(other)
            frontier = next_frontier
        return documents, links

    def _flow_date(self, value):
        if not value:
            return False
        return fields.Datetime.to_string(value) if isinstance(value, datetime) else fields.Date.to_string(value)

    def _flow_card(self, key, info):
        record = info['record']
        model = record._name
        card = {
            'key': f'{model},{record.id}', 'model': model, 'id': record.id,
            'name': record.display_name, 'model_label': record._description,
            'type': '', 'partner': '', 'amount': '', 'state': None,
            'depth': info['depth'], 'parent': info['parent'] and f'{info["parent"][0]},{info["parent"][1]}',
            'via': info['via'], 'created': self._flow_date(record.create_date), 'milestones': [],
        }
        for name in TYPE_FIELDS:
            if name in record._fields and record[name]:
                field = record._fields[name]
                card['type'] = (record[name].name or record[name].display_name if field.relational
                                else dict(field._description_selection(self.env)).get(record[name], ''))
                break
        if 'partner_id' in record._fields and record._fields['partner_id'].type == 'many2one':
            card['partner'] = record.partner_id.display_name or ''
        for name in AMOUNT_FIELDS:
            field = record._fields.get(name)
            if field and field.type == 'monetary' and record[name]:
                currency = record[field.get_currency_field(record)]
                card['amount'] = format_amount(self.env, record[name], currency) if currency else str(record[name])
                break
        if 'state' in record._fields and record._fields['state'].type == 'selection':
            selection = dict(record._fields['state']._description_selection(self.env))
            card['state'] = [record.state, selection.get(record.state, '')]
        elif 'stage_id' in record._fields and record.stage_id:
            card['state'] = ['stage', record.stage_id.display_name]
        if 'payment_state' in record._fields and record._fields['payment_state'].type == 'selection' \
                and record.payment_state:
            selection = dict(record._fields['payment_state']._description_selection(self.env))
            card['payment_state'] = [record.payment_state, selection.get(record.payment_state, '')]
        for name, label in MILESTONES.get(model, ()):
            if name in record._fields and record[name]:
                card['milestones'].append({
                    'field': name, 'label': label, 'date': self._flow_date(record[name]),
                    'planned': (model, name) in PLANNED,
                })
        return card

    def _flow_status_changes(self, documents):
        """ The status changes the chatter of the documents logged, oldest first. """
        events = []
        by_model = {}
        for model, res_id in documents:
            by_model.setdefault(model, []).append(res_id)
        for model, ids in by_model.items():
            Model = self.env[model]
            labels = {
                Model._fields[name]._description_string(self.env): name
                for name in TIMELINE_FIELDS if name in Model._fields
            }
            if not labels:
                continue
            # sudo: the documents were read by the user; their logs are not all theirs
            messages = self.env['mail.message'].sudo().search(
                [('model', '=', model), ('res_id', 'in', ids), ('message_type', 'in', ('tracking', 'notification'))],
                order='date asc, id asc', limit=500)
            for message in messages:
                for match in TRACKING_LINE.finditer(str(message.body or '')):
                    label = text(match['label'])
                    if label not in labels:
                        continue
                    events.append({
                        'key': f'{model},{message.res_id}', 'kind': 'status',
                        'date': self._flow_date(message.date),
                        'field': labels[label], 'label': label,
                        'old': text(match['old']), 'new': text(match['new']),
                        'author': message.author_id.display_name or '',
                    })
        return events

    @api.model
    def flow_of(self, model, res_id):
        start = self.env[model].browse(res_id).exists()
        start.check_access('read')
        documents, links = self._flow_links(start)
        cards = [self._flow_card(key, info) for key, info in documents.items()]
        events = []
        for card in cards:
            if card['created']:
                events.append({'key': card['key'], 'kind': 'created', 'date': card['created'],
                               'label': 'Created', 'author': documents[card['model'], card['id']]['record']
                               .create_uid.display_name or ''})
            for milestone in card['milestones']:
                if not milestone['planned']:
                    events.append({'key': card['key'], 'kind': 'milestone', 'date': milestone['date'],
                                   'label': milestone['label']})
        events += self._flow_status_changes(documents)
        # a date without a time (an invoice date) comes after the day's other events
        events.sort(key=lambda event: (
            (event['date'] or '') + (' 23:59:59' if len(event['date'] or '') <= 10 else ''),
            event['kind'] != 'created',
        ))
        # the journey, oldest first: the order, its deliveries, its invoices, their payments
        cards.sort(key=lambda card: (card['created'] or '', card['depth'], card['id']))
        return {
            'root': f'{start._name},{start.id}',
            'documents': cards,
            'links': [[f'{a[0]},{a[1]}', f'{b[0]},{b[1]}', label] for a, b, label in links],
            'events': events,
        }


# Going back on documents already saved: Odoo's own buttons, newest document
# first. Per model, the steps in order: (when it applies, method, label).
REVERSALS = {
    'account.payment': [
        (lambda record: record.state not in ('draft', 'canceled'), 'action_draft', 'Reset to draft'),
        (lambda record: record.state == 'draft', 'action_cancel', 'Cancel'),
    ],
    'account.move': [
        (lambda record: record.state == 'posted', 'button_draft', 'Reset to draft'),
        (lambda record: record.state == 'draft', 'button_cancel', 'Cancel'),
    ],
    'stock.picking': [
        (lambda record: record.state not in ('done', 'cancel'), 'action_cancel', 'Cancel'),
    ],
    'mrp.production': [
        (lambda record: record.state not in ('done', 'cancel'), 'action_cancel', 'Cancel'),
    ],
    'purchase.order': [
        (lambda record: record.state not in ('cancel',), 'button_cancel', 'Cancel'),
    ],
    'sale.order': [
        (lambda record: record.state not in ('cancel',), 'action_cancel', 'Cancel'),
    ],
}
# what cannot be gone back on, and what to do instead
BLOCKED = {
    'stock.picking': (lambda record: record.state == 'done',
                      "A done transfer cannot be undone: make a return from it."),
    'mrp.production': (lambda record: record.state == 'done',
                       "A done manufacturing order cannot be undone: unbuild it."),
}


class FlowVisualizerRewind(models.AbstractModel):
    _inherit = 'flow.visualizer.record'

    def _rewind_steps(self, record):
        """ The labels of what going back on ``record`` takes, as its state would go. """
        reversals = REVERSALS.get(record._name)
        blocked = BLOCKED.get(record._name)
        if blocked and blocked[0](record):
            return [], blocked[1]
        if not reversals:
            return [], "Odoo has no button to go back on this document."
        labels = []
        seen = record
        for applies, _method, label in reversals:
            if applies(seen):
                labels.append(label)
                # after a reset to draft, the next step sees a draft
                if label == 'Reset to draft':
                    seen = _Draft(record)
        return labels, ''

    def _rewind_targets(self, model, res_id, target_key):
        flow = self.flow_of(model, res_id)
        keys = [card['key'] for card in flow['documents']]
        if target_key not in keys:
            raise UserError(self.env._("This document is not in the flow anymore."))
        later = flow['documents'][keys.index(target_key) + 1:]
        # the newest first: a payment before its invoice
        return list(reversed(later))

    @api.model
    def rewind_plan(self, model, res_id, target_key):
        plan = []
        for card in self._rewind_targets(model, res_id, target_key):
            record = self.env[card['model']].browse(card['id'])
            labels, blocked = self._rewind_steps(record)
            if not labels and not blocked:
                continue
            plan.append({
                'key': card['key'], 'name': card['name'], 'model': card['model'],
                'model_label': card['type'] or card['model_label'],
                'state': card['state'], 'steps': labels, 'blocked': blocked,
            })
        return plan

    @api.model
    def rewind_apply(self, model, res_id, target_key):
        """ Go back on every document after the target that can be, all or none. """
        done = []
        with self.env.cr.savepoint():
            for card in self._rewind_targets(model, res_id, target_key):
                record = self.env[card['model']].browse(card['id'])
                blocked = BLOCKED.get(record._name)
                if blocked and blocked[0](record):
                    continue
                for applies, method, label in REVERSALS.get(record._name, ()):
                    record.invalidate_recordset()
                    if applies(record):
                        result = getattr(record, method)()
                        if isinstance(result, dict) and result.get('type') == 'ir.actions.act_window':
                            raise UserError(self.env._(
                                "%(name)s asks for more before it can be gone back on: do it from its form.",
                                name=card['name']))
                        done.append(f"{label}: {card['name']}")
        return done


class _Draft:
    """ A record seen as it will be once reset to draft. """

    def __init__(self, record):
        self._record = record

    def __getattr__(self, name):
        return 'draft' if name == 'state' else getattr(self._record, name)
