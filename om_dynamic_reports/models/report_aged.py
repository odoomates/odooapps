from collections import defaultdict
from odoo import api, fields, models, _, _lt


class OmDynamicReportAged(models.AbstractModel):
    """Aged balance: what each partner still owes (or is owed) at a date,
    spread over the days the open items are overdue; a partner unfolds into
    its open items.

    An item is open at the date when it was not reconciled yet, or was only
    reconciled after it; what is open is its balance less what was matched
    with it up to the date -- as in the PDF Aged Partner Balance.
    """
    _name = 'om.dynamic.report.aged'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Aged Balance'

    _report_section = 'partners'
    _report_date_mode = 'as_of'
    _report_default_preset = 'today'
    _report_group = 'account.group_account_invoice,account.group_account_readonly'
    # the account types of the report, and the sign that shows what is due as a positive amount
    _odr_account_types = ()
    _odr_sign = 1

    @api.model
    def _om_name_label(self, options):
        return _("Partner")

    @api.model
    def _om_filters(self):
        filters = self._odr_filters('partner_ids', 'partner_category_ids', 'account_ids', 'journal_ids')
        for spec in filters:
            if spec['key'] == 'account_ids':
                spec['domain'] = spec['domain'] + [('account_type', 'in', list(self._odr_account_types))]
        return filters

    @api.model
    def _om_choices(self):
        return [
            self._odr_target_move_choice(),
            {'key': 'aging_basis', 'label': _("Age by"), 'icon': 'event', 'menu': 'bar',
             'default': 'due', 'choices': [['due', _("Due date")],
                                           ['invoice', _("Invoice date")]]},
        ]

    @api.model
    def _om_numbers(self):
        return [
            {'key': 'period_length', 'label': _("Days per period"), 'default': 30, 'min': 1, 'max': 366},
            {'key': 'period_count', 'label': _("Number of periods"), 'default': 4, 'min': 1, 'max': 12},
        ]

    # ------------------------------------------------------------------
    # Periods and columns
    # ------------------------------------------------------------------

    @api.model
    def _odr_buckets(self, options):
        """[(key, label, first day overdue, last day overdue)]: not due, the periods, then older."""
        length, count = options['period_length'], options['period_count']
        buckets = [('not_due', _("Not Due"), None, 0)]
        for index in range(count):
            first, last = index * length + 1, (index + 1) * length
            buckets.append(('period_%s' % index, '%s-%s' % (first, last), first, last))
        buckets.append(('older', _("Older"), count * length + 1, None))
        return buckets

    @api.model
    def _om_get_columns(self, options):
        columns = [
            {'key': 'date', 'label': _("Invoice Date"), 'type': 'date', 'detail_only': True},
            {'key': 'date_maturity', 'label': _("Due Date"), 'type': 'date', 'detail_only': True},
            {'key': 'journal', 'label': _("Journal"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'account', 'label': _("Account"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'label', 'label': _("Reference"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'days', 'label': _("Days Overdue"), 'type': 'int', 'detail_only': True},
        ]
        for key, label, _first, _last in self._odr_buckets(options):
            columns.append({'key': key, 'label': label, 'type': 'monetary', 'blank_zero': True,
                            'group': _("Overdue") if key.startswith('period_') or key == 'older' else False})
        columns.append({'key': 'total', 'label': _("Total"), 'type': 'monetary', 'optional': False})
        return columns

    # ------------------------------------------------------------------
    # Open items
    # ------------------------------------------------------------------

    @api.model
    def _odr_open_items_domain(self, options):
        date = options['date_to']
        domain = [
            ('company_id', 'in', self._odr_company_ids()),
            ('account_id.account_type', 'in', list(self._odr_account_types)),
            ('date', '<=', date),
            ('parent_state', '=', 'posted') if options['target_move'] == 'posted'
            else ('parent_state', 'in', ('draft', 'posted')),
            '|', '|', ('reconciled', '=', False),
            ('matched_debit_ids.max_date', '>', date), ('matched_credit_ids.max_date', '>', date),
        ]
        if options['partner_ids']:
            domain.append(('partner_id', 'in', options['partner_ids']))
        if options['partner_category_ids']:
            domain.append(('partner_id.category_id', 'in', options['partner_category_ids']))
        if options['account_ids']:
            domain.append(('account_id', 'in', options['account_ids']))
        if options['journal_ids']:
            domain.append(('journal_id', 'in', options['journal_ids']))
        return domain

    @api.model
    def _odr_matched_until(self, line_ids, date, side):
        """{line id: amount reconciled with it up to ``date``}; ``side`` is the field of the
        partial reconciliation holding the line (debit_move_id or credit_move_id)."""
        if not line_ids:
            return {}
        groups = self.env['account.partial.reconcile']._read_group(
            [(side, 'in', line_ids), ('max_date', '<=', date)], [side], ['amount:sum'])
        return {line.id: amount for line, amount in groups}

    @api.model
    def _odr_open_items(self, options):
        """The open items at the date, as plain values (they are kept in the cache of the engine):
        [{'id', 'partner_id', 'move_id', 'name', 'amount', 'days', 'bucket', 'values'}], the amounts
        signed for the report."""
        date = fields.Date.to_date(options['date_to'])
        lines = self.env['account.move.line'].search_fetch(
            self._odr_open_items_domain(options),
            ['date', 'date_maturity', 'move_name', 'move_id', 'journal_id', 'account_id', 'partner_id', 'ref',
             'name', 'balance', 'company_id'], order='date, move_name, id')
        # what was matched until the date: with a debit item from the credit side, and the other way round
        matched_debit = self._odr_matched_until(lines.ids, date, 'credit_move_id')
        matched_credit = self._odr_matched_until(lines.ids, date, 'debit_move_id')
        currency = self._om_currency()
        buckets = self._odr_buckets(options)
        items = []
        for line in lines:
            # the amounts reconciled with an item are in the currency of its company, as its balance
            amount = line.balance + matched_debit.get(line.id, 0.0) - matched_credit.get(line.id, 0.0)
            amount = self._odr_convert(amount, line.company_id)
            if currency.is_zero(amount):
                continue
            reference = line.date if options['aging_basis'] == 'invoice' else (line.date_maturity or line.date)
            days = (date - reference).days
            bucket = next(key for key, _label, first, last in buckets
                          if (first is None or days >= first) and (last is None or days <= last))
            amount = currency.round(amount * self._odr_sign)
            items.append({
                'id': line.id,
                'partner_id': line.partner_id.id or 0,
                'move_id': line.move_id.id,
                'name': line.move_name or '',
                'amount': amount,
                'bucket': bucket,
                'values': {
                    'date': fields.Date.to_string(line.date),
                    'date_maturity': line.date_maturity and fields.Date.to_string(line.date_maturity),
                    'journal': line.journal_id.code,
                    'account': self._odr_account_code(line.account_id),
                    'label': self._odr_label(line),
                    'days': max(days, 0),
                    bucket: amount,
                    'total': amount,
                },
            })
        return items

    @api.model
    def _om_compute(self, options):
        items = self._odr_open_items(options)
        tree, total = self._odr_aged_tree(items, options)
        if options['search']:
            tree = self._om_search_tree(tree, options['search'])
        return {'tree': tree, 'total': total, 'items': items}

    @api.model
    def _odr_aged_tree(self, items, options):
        bucket_keys = [key for key, _label, _first, _last in self._odr_buckets(options)]
        by_partner = defaultdict(list)
        for item in items:
            by_partner[item['partner_id']].append(item)
        partners = self.env['res.partner'].with_context(active_test=False).browse(
            [partner_id for partner_id in by_partner if partner_id])
        names = {partner.id: partner.display_name for partner in partners}
        order = sorted(by_partner, key=lambda pid: (not pid, (names.get(pid) or '').casefold()))
        currency = self._om_currency()
        nodes = []
        total = dict.fromkeys(bucket_keys + ['total'], 0.0)
        for partner_id in order:
            values = dict.fromkeys(bucket_keys + ['total'], 0.0)
            for item in by_partner[partner_id]:
                values[item['bucket']] += item['amount']
                values['total'] += item['amount']
            if currency.is_zero(values['total']) and all(currency.is_zero(values[k]) for k in bucket_keys):
                continue
            for key in values:
                total[key] += values[key]
            line_id = 'partner-%s' % partner_id
            name = names.get(partner_id) or _("Unknown Partner")
            links = []
            if partner_id:
                links.append(self._om_link('om.dynamic.report.partner.ledger', _("Open Partner Ledger"), {
                    'partner_ids': [partner_id], 'target_move': options['target_move'],
                    'result_selection': 'customer' if 'asset_receivable' in self._odr_account_types else 'supplier',
                    'date_preset': 'custom', 'date_to': options['date_to'],
                    'date_from': str(self._odr_fiscal_year_start(options['date_to'])),
                }, icon='person'))
            line = self._om_line(line_id, name, values, kind='leaf', has_children=True,
                                 open_record=('res.partner', partner_id) if partner_id else False,
                                 drill=True, drill_label=_("Open items"), links=links,
                                 count=len(by_partner[partner_id]))
            nodes.append(self._odr_node(line_id, name, line))
        return nodes, total if nodes else False

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        partner_id = self._odr_line_id_part(line['id'], 'partner')
        items = [item for item in data['items'] if item['partner_id'] == partner_id]
        page, more = self._om_page(items, offset, limit)
        return [self._om_line('%s|aml-%s' % (line['id'], item['id']), item['name'], item['values'],
                              parent_id=line['id'], level=1, kind='detail',
                              open_record=('account.move', item['move_id'])) for item in page], more

    @api.model
    def _om_line_action(self, options, line_id):
        partner_id = self._odr_line_id_part(line_id, 'partner')
        if partner_id is False:
            return False
        data = self._om_compute_cached(options)
        items = [item['id'] for item in data['items'] if item['partner_id'] == partner_id]
        partner = self.env['res.partner'].browse(partner_id) if partner_id else False
        name = partner.display_name if partner else _("Unknown Partner")
        return self._odr_journal_items_action([('id', 'in', items)], name)


class OmDynamicReportAgedReceivable(models.AbstractModel):
    _name = 'om.dynamic.report.aged.receivable'
    _inherit = 'om.dynamic.report.aged'
    _description = 'Dynamic Aged Receivable'

    _report_name = 'Aged Receivable'
    _report_description = _lt("What customers owe, by how long it is overdue.")
    _report_sequence = 40
    _report_icon = 'call_received'
    _odr_account_types = ('asset_receivable',)
    _odr_sign = 1

    @api.model
    def _om_report_title(self):
        return _("Aged Receivable")


class OmDynamicReportAgedPayable(models.AbstractModel):
    _name = 'om.dynamic.report.aged.payable'
    _inherit = 'om.dynamic.report.aged'
    _description = 'Dynamic Aged Payable'

    _report_name = 'Aged Payable'
    _report_description = _lt("What is owed to vendors, by how long it is overdue.")
    _report_sequence = 41
    _report_icon = 'call_made'
    # what is owed to the vendors shows as a positive amount
    _odr_account_types = ('liability_payable',)
    _odr_sign = -1

    @api.model
    def _om_report_title(self):
        return _("Aged Payable")
