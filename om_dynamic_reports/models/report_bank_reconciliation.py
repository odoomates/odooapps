from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmDynamicReportBankReconciliation(models.AbstractModel):
    """Bank Reconciliation: per bank and cash journal, at a date, the bank
    balance of the books against the last bank statement, what is not on a
    statement yet, the bank transactions still to match, the payments
    registered that the bank has not shown yet, and the balance once all of
    it is matched.

    In Odoo the bank account only moves with the bank transactions: the
    payments wait on the outstanding receipts and payments accounts until they
    are matched with a transaction, and an unmatched transaction waits on the
    suspense account. What is open on those accounts at the date is what is
    still to match -- open as in the aged reports: not reconciled yet, or
    reconciled after the date.
    """
    _name = 'om.dynamic.report.bank.reconciliation'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Bank Reconciliation'

    _report_name = 'Bank Reconciliation'
    _report_description = _lt("Books against bank statements, and what is still to match, per bank account.")
    _report_section = 'ledgers'
    _report_sequence = 25
    _report_icon = 'account_balance'
    _report_date_mode = 'as_of'
    _report_default_preset = 'today'

    @api.model
    def _om_report_title(self):
        return self.env._("Bank Reconciliation")

    @api.model
    def _om_name_label(self, options):
        return ''

    @api.model
    def _om_filters(self):
        spec = self._odr_filter('journal_ids')
        spec['domain'] = spec['domain'] + [('type', 'in', ('bank', 'cash'))]
        return [spec]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'label', 'label': self.env._("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'partner', 'label': self.env._("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'amount', 'label': self.env._("Amount"), 'type': 'monetary', 'optional': False},
        ]

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_journals(self, options):
        domain = [('type', 'in', ('bank', 'cash')), ('company_id', 'in', self._odr_company_ids())]
        if options['journal_ids']:
            domain.append(('id', 'in', options['journal_ids']))
        return self.env['account.journal'].search(domain, order='sequence, id')

    @api.model
    def _odr_outstanding_accounts(self, journal):
        return (journal._get_journal_inbound_outstanding_payment_accounts()
                | journal._get_journal_outbound_outstanding_payment_accounts())

    @api.model
    def _odr_open_items(self, journal, accounts, date):
        """[(line, open amount)] of the journal on ``accounts`` still open at ``date``."""
        if not accounts:
            return []
        lines = self.env['account.move.line'].search(
            [('journal_id', '=', journal.id), ('account_id', 'in', accounts.ids), ('parent_state', '=', 'posted'),
             ('date', '<=', date)] + self._odr_open_domain(date), order='date, id')
        amounts = self._odr_open_amounts(lines, date)
        currency = self._om_currency()
        return [(line, amounts[line.id]) for line in lines if not currency.is_zero(amounts[line.id])]

    @api.model
    def _odr_item(self, line, amount, sign=1):
        statement_line = line.move_id.statement_line_id
        return {
            'id': line.id,
            'move_id': line.move_id.id,
            'name': line.move_id.name or '',
            'values': {
                'date': fields.Date.to_string(line.date),
                'label': (statement_line.payment_ref if statement_line else '') or self._odr_label(line),
                'partner': line.partner_id.display_name or '',
                'amount': amount * sign,
            },
        }

    @api.model
    def _odr_journal_figures(self, journal, date):
        currency = self._om_currency()
        bank_account = journal.default_account_id
        books = sum(sums['balance'] for sums in self._odr_sums(
            [('account_id', '=', bank_account.id), ('journal_id', '=', journal.id), ('parent_state', '=', 'posted'),
             ('date', '<=', date)], 'company_id').values()) if bank_account else 0.0
        statement = self.env['account.bank.statement'].search(
            [('journal_id', '=', journal.id), ('date', '<=', date)], order='date desc, id desc', limit=1)
        # the statement is in the currency of the journal
        statement_balance = statement.currency_id._convert(
            statement.balance_end_real, currency, self.env.company, date, round=False) if statement else 0.0
        # an unmatched transaction waits on the suspense account, against the bank: its bank side
        suspense = self._odr_open_items(journal, journal.suspense_account_id, date)
        unmatched = [self._odr_item(line, amount, sign=-1) for line, amount in suspense]
        outstanding = [self._odr_item(line, amount)
                       for line, amount in self._odr_open_items(journal, self._odr_outstanding_accounts(journal), date)]
        receipts = [item for item in outstanding if item['values']['amount'] > 0]
        payments = [item for item in outstanding if item['values']['amount'] < 0]
        outstanding_total = sum(item['values']['amount'] for item in outstanding)
        return {
            'books': currency.round(books),
            'statement': statement,
            'statement_balance': currency.round(statement_balance),
            'not_on_statement': currency.round(books - statement_balance),
            'unmatched_receipts': [item for item in unmatched if item['values']['amount'] > 0],
            'unmatched_payments': [item for item in unmatched if item['values']['amount'] < 0],
            'outstanding_receipts': receipts,
            'outstanding_payments': payments,
            'once_matched': currency.round(books + outstanding_total),
        }

    @api.model
    def _om_compute(self, options):
        date = options['date_to']
        nodes = []
        details = {}
        currency = self._om_currency()
        for journal in self._odr_journals(options):
            figures = self._odr_journal_figures(journal, date)
            journal_id = 'journal-%s' % journal.id
            statement = figures['statement']
            rows = []

            def row(key, name, amount, kind='leaf', items=None, drill=False, record=False):
                line_id = '%s|%s' % (journal_id, key)
                if items is not None:
                    details[line_id] = items
                rows.append(self._odr_node(line_id, name, self._om_line(
                    line_id, name, {'amount': amount}, parent_id=journal_id, level=1,
                    kind='group' if items else kind, has_children=bool(items), count=len(items or []),
                    drill=drill, open_record=record)))

            row('books', self.env._("Bank balance in the books"), figures['books'], drill=True)
            if statement:
                row('statement', self.env._("Last statement: %(name)s, %(date)s", name=statement.name,
                                            date=self._om_format_date(statement.date)),
                    figures['statement_balance'], record=('account.bank.statement', statement.id))
            else:
                row('statement', self.env._("No bank statement yet"), 0.0)
            row('not_on_statement', self.env._("Transactions not in a statement"), figures['not_on_statement'],
                drill=not currency.is_zero(figures['not_on_statement']))
            for key, name in (('unmatched_receipts', self.env._("Bank receipts to match")),
                              ('unmatched_payments', self.env._("Bank payments to match")),
                              ('outstanding_receipts', self.env._("Outstanding receipts")),
                              ('outstanding_payments', self.env._("Outstanding payments"))):
                items = figures[key]
                row(key, name, sum(item['values']['amount'] for item in items), items=items)
            row('once_matched', self.env._("Bank balance once all is matched"), figures['once_matched'],
                kind='closing')
            name = '%s (%s)' % (journal.name, journal.code)
            nodes.append(self._odr_node(journal_id, name, self._om_line(
                journal_id, name, {'amount': figures['books']}, kind='group', has_children=True,
                count=len(rows), unfolded=True, open_record=('account.journal', journal.id)), rows))
        if options['search']:
            nodes = self._om_search_tree(nodes, options['search'])
        return {'tree': nodes, 'total': False, 'details': details}

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        items = data['details'].get(line['id'], [])
        page, more = self._om_page(items, offset, limit)
        return [self._om_line('%s|aml-%s' % (line['id'], item['id']), item['name'], item['values'],
                              parent_id=line['id'], level=line['level'] + 1, kind='detail',
                              open_record=('account.move', item['move_id'])) for item in page], more

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    @api.model
    def _om_line_action(self, options, line_id):
        journal = self.env['account.journal'].browse(self._odr_line_id_part(line_id, 'journal')).exists()
        if not journal or not journal.default_account_id:
            return False
        domain = [('account_id', '=', journal.default_account_id.id), ('journal_id', '=', journal.id),
                  ('parent_state', '=', 'posted'), ('date', '<=', options['date_to'])]
        name = journal.display_name
        if line_id.endswith('|not_on_statement'):
            statement = self.env['account.bank.statement'].search(
                [('journal_id', '=', journal.id), ('date', '<=', options['date_to'])],
                order='date desc, id desc', limit=1)
            # the transactions of no statement, or of none up to the last one
            domain += ['|', ('statement_id', '=', False), ('date', '>', statement.date)] if statement \
                else [('statement_id', '=', False)]
            name = self.env._("%s: not in a statement", journal.display_name)
        return self._odr_journal_items_action(domain, name)
