from odoo import api, fields, models, _, _lt


class OmDynamicReportDayBook(models.AbstractModel):
    """Day Book: day by day, every journal item of the period with its entry,
    journal, account and partner, and the debit and credit of each day, as the
    PDF Day Book of Daily Reports prints them."""
    _name = 'om.dynamic.report.day.book'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Day Book'

    _report_name = 'Day Book'
    _report_description = _lt("Every journal item, day by day.")
    _report_section = 'ledgers'
    _report_sequence = 21
    _report_icon = 'today'
    _report_default_preset = 'this_month'

    @api.model
    def _om_report_title(self):
        return _("Day Book")

    @api.model
    def _om_name_label(self, options):
        return _("Day")

    @api.model
    def _om_filters(self):
        return self._odr_filters('journal_ids', 'account_ids', 'partner_ids')

    @api.model
    def _om_choices(self):
        return [self._odr_target_move_choice()]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'journal', 'label': _("Journal"), 'type': 'char', 'detail_only': True},
            {'key': 'account', 'label': _("Account"), 'type': 'char', 'detail_only': True},
            {'key': 'partner', 'label': _("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'label', 'label': _("Label"), 'type': 'char', 'detail_only': True},
            {'key': 'debit', 'label': _("Debit"), 'type': 'monetary', 'blank_zero': True},
            {'key': 'credit', 'label': _("Credit"), 'type': 'monetary', 'blank_zero': True},
        ]

    @api.model
    def _odr_day_domain(self, options):
        return self._odr_domain(options) + self._odr_period_domain(options)

    @api.model
    def _om_compute(self, options):
        domain = self._odr_day_domain(options)
        sums = self._odr_sums(domain, 'date:day')
        counts = dict(self._om_read_group(self.env['account.move.line'], domain, ['date:day'], ['__count']))
        nodes = []
        total = {'debit': 0.0, 'credit': 0.0}
        for day in sorted(sums):
            values = {'debit': sums[day]['debit'], 'credit': sums[day]['credit']}
            for key in total:
                total[key] += values[key]
            line_id = 'day-%s' % day.strftime('%Y%m%d')
            name = self._om_format_date(day)
            nodes.append(self._odr_node(line_id, name, self._om_line(
                line_id, name, values, kind='group', has_children=True, count=counts.get(day, 0), drill=True,
                day=fields.Date.to_string(day))))
        if options['search']:
            nodes = self._om_search_tree(nodes, options['search'])
        return {'tree': nodes, 'total': total if nodes else False}

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        domain = self._odr_day_domain(options) + [('date', '=', line['day'])]
        MoveLine = self.env['account.move.line']
        count = MoveLine.search_count(domain)
        items = self._om_search_fetch(MoveLine, domain, ['move_name', 'move_id', 'journal_id', 'account_id', 'partner_id', 'name', 'ref', 'debit',
                     'credit', 'company_id'], order='move_name, id', offset=offset, limit=limit or None)
        lines = [self._om_line('%s|aml-%s' % (line['id'], item.id), item.move_name or '', {
            'journal': item.journal_id.code,
            'account': self._odr_account_name(item.account_id),
            'partner': item.partner_id.display_name or '',
            'label': self._odr_label(item),
            'debit': self._odr_convert(item.debit, item.company_id),
            'credit': self._odr_convert(item.credit, item.company_id),
        }, parent_id=line['id'], level=1, kind='detail', open_record=('account.move', item.move_id.id))
            for item in items]
        return lines, max(count - offset - len(items), 0)

    @api.model
    def _om_line_action(self, options, line_id):
        day = line_id.rpartition('day-')[2]
        if not day.isdigit():
            return False
        day = fields.Date.to_date('%s-%s-%s' % (day[:4], day[4:6], day[6:]))
        return self._odr_journal_items_action(self._odr_day_domain(options) + [('date', '=', day)],
                                              '%s %s' % (self._om_report_title(), self._om_format_date(day)))
