from odoo import api, fields, models, _, _lt
from odoo.tools.misc import format_amount

from odoo.addons.om_report_engine.models.report import PAGE_SIZE

ENTRY_ORDERS = {'date': 'date, name, id', 'move_name': 'name, id'}


class OmDynamicReportJournalAudit(models.AbstractModel):
    """Journals Audit: every journal with its debit and credit over the
    period; a journal unfolds into its entries, an entry into its journal
    items, and the taxes of the journal are summed at the end, as the PDF
    Journals Audit prints them."""
    _name = 'om.dynamic.report.journal.audit'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Journals Audit'

    _report_name = 'Journals Audit'
    _report_description = _lt("Every journal, entry by entry, with its taxes.")
    _report_section = 'ledgers'
    _report_sequence = 30
    _report_icon = 'fact_check'

    @api.model
    def _om_report_title(self):
        return _("Journals Audit")

    @api.model
    def _om_name_label(self, options):
        return _("Journal")

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'partner_ids')

    @api.model
    def _om_choices(self):
        return [
            self._odr_target_move_choice(),
            {'key': 'sort_selection', 'label': _("Sort entries by"), 'default': 'date', 'choices': [
                ['date', _("Date")], ['move_name', _("Entry number")]]},
        ]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': _("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'account', 'label': _("Account"), 'type': 'char', 'detail_only': True},
            {'key': 'partner', 'label': _("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'label', 'label': _("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'debit', 'label': _("Debit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'credit', 'label': _("Credit"), 'type': 'monetary', 'blank_zero': True},
        ]

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_journal_domain(self, options):
        return self._odr_domain(options) + self._odr_period_domain(options)

    @api.model
    def _om_compute(self, options):
        domain = self._odr_journal_domain(options)
        sums = self._odr_sums(domain, 'journal_id')
        entry_counts = {journal.id: count for journal, count in self.env['account.move.line']._read_group(
            domain, ['journal_id'], ['move_id:count_distinct'])}
        journals = self.env['account.journal'].with_context(active_test=False).browse(list(sums))
        nodes = []
        total = {'debit': 0.0, 'credit': 0.0}
        for journal in journals.sorted(lambda j: (j.sequence, j.code or '')):
            values = {'debit': sums[journal.id]['debit'], 'credit': sums[journal.id]['credit']}
            for key in total:
                total[key] += values[key]
            line_id = 'journal-%s' % journal.id
            name = '%s (%s)' % (journal.name, journal.code)
            nodes.append(self._odr_node(line_id, name, self._om_line(
                line_id, name, values, kind='group', has_children=True, count=entry_counts.get(journal.id, 0),
                drill=True, open_record=('account.journal', journal.id))))
        if options['search']:
            nodes = self._om_search_tree(nodes, options['search'])
        return {'tree': nodes, 'total': total if nodes else False}

    @api.model
    def _om_lines(self, data, options, parent_id=False, offset=0, limit=PAGE_SIZE):
        # the entries and the taxes of a journal are not nodes of the tree: their lines come from here
        if parent_id and ('|move-' in parent_id or parent_id.endswith('|taxes')):
            return self._odr_detail_lines(data, options, {'id': parent_id, 'level': parent_id.count('|')},
                                          offset, limit)
        return super()._om_lines(data, options, parent_id, offset, limit)

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        move_id = self._odr_line_id_part(line['id'], 'move')
        if move_id:
            return self._odr_entry_items(options, line, move_id), 0
        journal_id = self._odr_line_id_part(line['id'], 'journal')
        if line['id'].endswith('|taxes'):
            return self._odr_journal_tax_lines(options, line, journal_id), 0
        return self._odr_journal_entries(options, line, journal_id, offset, limit)

    @api.model
    def _odr_journal_entries(self, options, line, journal_id, offset, limit):
        """The entries of a journal, page by page, then its taxes."""
        domain = self._odr_journal_domain(options) + [('journal_id', '=', journal_id)]
        Move = self.env['account.move']
        move_domain = [('line_ids', 'any', domain)]
        count = Move.search_count(move_domain)
        moves = Move.search(move_domain, order=ENTRY_ORDERS[options['sort_selection']], offset=offset,
                            limit=limit or None)
        sums = self._odr_sums(domain + [('move_id', 'in', moves.ids)], 'move_id')
        lines = []
        for move in moves:
            entry_id = '%s|move-%s' % (line['id'], move.id)
            values = {'date': fields.Date.to_string(move.date), 'partner': move.partner_id.display_name or '',
                      'label': move.ref or '', 'debit': sums.get(move.id, {}).get('debit', 0.0),
                      'credit': sums.get(move.id, {}).get('credit', 0.0)}
            # an entry shows its date, partner and reference like a detail line, and unfolds into its items
            lines.append(self._om_line(entry_id, move.name or '', values, parent_id=line['id'],
                                       level=line['level'] + 1, kind='detail', has_children=True,
                                       open_record=('account.move', move.id)))
        more = max(count - offset - len(moves), 0)
        if not more:
            # the taxes of the journal, after its last entry
            taxes_id = '%s|taxes' % line['id']
            if self._odr_journal_tax_lines(options, {'id': taxes_id, 'level': line['level'] + 1}, journal_id):
                lines.append(self._om_line(taxes_id, _("Taxes"), {}, parent_id=line['id'],
                                           level=line['level'] + 1, kind='group', has_children=True))
        return lines, more

    @api.model
    def _odr_entry_items(self, options, line, move_id):
        items = self.env['account.move.line'].search(
            self._odr_journal_domain(options) + [('move_id', '=', move_id)], order='id')
        return [self._om_line('%s|aml-%s' % (line['id'], item.id), self._odr_account_name(item.account_id), {
            'date': fields.Date.to_string(item.date),
            'account': self._odr_account_code(item.account_id),
            'partner': item.partner_id.display_name or '',
            'label': item.name or '',
            'debit': self._odr_convert(item.debit, item.company_id),
            'credit': self._odr_convert(item.credit, item.company_id),
        }, parent_id=line['id'], level=line['level'] + 1, kind='detail',
            open_record=('account.move', item.move_id.id)) for item in items]

    @api.model
    def _odr_journal_tax_lines(self, options, line, journal_id):
        """Base and tax of each tax of the journal, signed as sales on a sale journal."""
        journal = self.env['account.journal'].browse(journal_id)
        domain = self._odr_journal_domain(options) + [('journal_id', '=', journal_id)]
        sign = -1 if journal.type == 'sale' else 1
        bases = self._odr_sums(domain + [('tax_ids', '!=', False)], 'tax_ids')
        amounts = self._odr_sums(domain + [('tax_line_id', '!=', False)], 'tax_line_id')
        taxes = self.env['account.tax'].with_context(active_test=False).browse(set(bases) | set(amounts))
        return [self._om_line('%s|tax-%s' % (line['id'], tax.id), tax.name, {
            'label': _(
                "Base %(base)s · Tax %(tax)s",
                base=self._odr_format_amount(bases.get(tax.id, {}).get('balance', 0.0) * sign),
                tax=self._odr_format_amount(amounts.get(tax.id, {}).get('balance', 0.0) * sign)),
            'base': bases.get(tax.id, {}).get('balance', 0.0) * sign,
            'tax': amounts.get(tax.id, {}).get('balance', 0.0) * sign,
        }, parent_id=line['id'], level=line['level'] + 1, kind='detail', open_record=('account.tax', tax.id))
            for tax in taxes.sorted(lambda t: (t.sequence, t.name or ''))]

    @api.model
    def _odr_format_amount(self, amount):
        return format_amount(self.env, amount, self._om_currency())

    @api.model
    def _om_line_action(self, options, line_id):
        journal_id = self._odr_line_id_part(line_id, 'journal')
        if not journal_id:
            return False
        journal = self.env['account.journal'].browse(journal_id)
        return self._odr_journal_items_action(self._odr_journal_domain(options) + [('journal_id', '=', journal_id)],
                                              journal.display_name)
