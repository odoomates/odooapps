from collections import defaultdict

from markupsafe import Markup

from odoo import api, fields, models, _, _lt

DETAIL_FIELDS = ['date', 'date_maturity', 'move_name', 'move_id', 'ref', 'name', 'balance', 'partner_id', 'company_id']


class OmDynamicReportStatement(models.AbstractModel):
    """Statement of account, to send to a partner: per partner, either every
    entry of the period between the opening and the closing balance
    (activity), or the items still open at the date (open items); then what is
    due, by how long it is overdue.

    Amounts are signed for the partner's side of the story: on a customer
    statement an invoice is a charge and a payment a payment, and the balance is
    what the customer owes; on a vendor statement the balance is what is owed
    to the vendor.
    """
    _name = 'om.dynamic.report.statement'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Partner Statement'

    _report_section = 'partners'
    _report_default_preset = 'this_month'
    _report_group = 'account.group_account_invoice,account.group_account_readonly'
    # the aged report giving the open items, and the sign showing what is due as a positive amount
    _odr_aged_model = False
    _odr_sign = 1
    # partners unfolded when the statement opens, at most
    _odr_unfold_limit = 10

    @api.model
    def _om_name_label(self, options):
        return _("Partner")

    @api.model
    def _om_filters(self):
        return self._odr_filters('partner_ids', 'partner_category_ids')

    @api.model
    def _om_choices(self):
        return [
            {'key': 'statement_type', 'label': _("Statement"), 'icon': 'receipt_long', 'menu': 'bar',
             'default': 'activity', 'choices': [
                 ['activity', _("Activity")],
                 ['open', _("Open items")],
             ]},
            self._odr_target_move_choice(),
        ]

    @api.model
    def _om_toggles(self):
        return [{'key': 'ageing', 'label': _("Ageing summary"), 'default': True,
                 'help': _("What is due at the end of the period, by how long it is overdue.")}]

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': _("Date"), 'type': 'date', 'detail_only': True},
            {'key': 'label', 'label': _("Reference"), 'type': 'char', 'detail_only': True},
            {'key': 'date_maturity', 'label': _("Due Date"), 'type': 'date', 'detail_only': True},
            {'key': 'charge', 'label': self._odr_charge_label(), 'type': 'monetary', 'blank_zero': True},
            {'key': 'payment', 'label': self._odr_payment_label(), 'type': 'monetary', 'blank_zero': True},
            {'key': 'balance', 'label': _("Balance"), 'type': 'monetary', 'optional': False},
        ]

    @api.model
    def _odr_charge_label(self):
        return _("Charge")

    @api.model
    def _odr_payment_label(self):
        return _("Payment")

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_aged(self):
        return self.env[self._odr_aged_model]

    @api.model
    def _odr_aged_options(self, options):
        return self._odr_aged()._om_normalize_options({
            'date_preset': 'custom', 'date_to': options['date_to'], 'target_move': options['target_move'],
            'partner_ids': options['partner_ids'], 'partner_category_ids': options['partner_category_ids'],
        })

    @api.model
    def _odr_partner_domain(self, options):
        domain = [
            ('company_id', 'in', self._odr_company_ids()),
            ('partner_id', '!=', False),
            ('account_id.account_type', 'in', list(self._odr_aged()._odr_account_types)),
            ('parent_state', '=', 'posted') if options['target_move'] == 'posted'
            else ('parent_state', 'in', ('draft', 'posted')),
        ]
        if options['partner_ids']:
            domain.append(('partner_id', 'in', options['partner_ids']))
        if options['partner_category_ids']:
            domain.append(('partner_id.category_id', 'in', options['partner_category_ids']))
        return domain

    @api.model
    def _odr_split(self, amount):
        """(charge, payment) of an amount signed for the statement."""
        return max(amount, 0.0), max(-amount, 0.0)

    @api.model
    def _om_compute(self, options):
        sign = self._odr_sign
        aged_options = self._odr_aged_options(options)
        open_items = self._odr_aged()._odr_open_items(aged_options)
        buckets = self._odr_aged()._odr_buckets(aged_options)
        ageing = defaultdict(lambda: defaultdict(float))
        open_by_partner = defaultdict(list)
        for item in open_items:
            if item['partner_id']:
                ageing[item['partner_id']][item['bucket']] += item['amount']
                open_by_partner[item['partner_id']].append(item)

        partners_values = {}
        if options['statement_type'] == 'activity':
            domain = self._odr_partner_domain(options)
            opening = self._odr_sums(domain + [('date', '<', options['date_from'])], 'partner_id')
            period = domain + self._odr_period_domain(options)
            debit = self._odr_sums(period + [('balance', '>', 0)], 'partner_id')
            credit = self._odr_sums(period + [('balance', '<', 0)], 'partner_id')
            for partner_id in set(opening) | set(debit) | set(credit):
                start = opening.get(partner_id, {}).get('balance', 0.0) * sign
                moves = [debit.get(partner_id, {}).get('balance', 0.0) * sign,
                         credit.get(partner_id, {}).get('balance', 0.0) * sign]
                charge = sum(amount for amount in moves if amount > 0)
                payment = -sum(amount for amount in moves if amount < 0)
                partners_values[partner_id] = {'opening': start, 'charge': charge, 'payment': payment,
                                               'balance': start + charge - payment}
        else:
            for partner_id, items in open_by_partner.items():
                charge = sum(item['amount'] for item in items if item['amount'] > 0)
                payment = -sum(item['amount'] for item in items if item['amount'] < 0)
                partners_values[partner_id] = {'opening': 0.0, 'charge': charge, 'payment': payment,
                                               'balance': charge - payment}

        currency = self._om_currency()
        partners = self.env['res.partner'].with_context(active_test=False).browse(list(partners_values))
        shown = [partner for partner in partners.sorted(lambda p: (p.display_name or '').casefold())
                 if not all(currency.is_zero(value) for value in partners_values[partner.id].values())]
        nodes = []
        total = {'charge': 0.0, 'payment': 0.0, 'balance': 0.0}
        for partner in shown:
            values = partners_values[partner.id]
            line_id = 'partner-%s' % partner.id
            line = self._om_line(
                line_id, partner.display_name, {key: values[key] for key in ('charge', 'payment', 'balance')},
                kind='leaf', has_children=True, open_record=('res.partner', partner.id),
                unfolded=len(shown) <= self._odr_unfold_limit, opening=values['opening'],
                actions=[
                    {'key': 'download', 'label': _("Download the statement (PDF)"),
                     'icon': 'picture_as_pdf'},
                    {'key': 'email', 'label': _("Send the statement by email"), 'icon': 'mail'},
                ])
            nodes.append(self._odr_node(line_id, partner.display_name, line))
            for key in total:
                total[key] += values[key]
        if options['search']:
            nodes = self._om_search_tree(nodes, options['search'])
        return {
            'tree': nodes,
            'total': total if nodes else False,
            'open_items': {partner_id: items for partner_id, items in open_by_partner.items()},
            'ageing': {partner_id: dict(amounts) for partner_id, amounts in ageing.items()},
            'buckets': [(key, self._odr_bucket_label(key, label, first)) for key, label, first, _last in buckets],
        }

    @api.model
    def _odr_detail_lines(self, data, options, line, offset, limit):
        """The whole statement of a partner: it is read at once, a partner has a few lines."""
        partner_id = self._odr_line_id_part(line['id'], 'partner')
        parent = {'id': line['id'], 'level': line['level']}
        rows = []

        def add(key, name, values, kind, open_record=False):
            rows.append(self._om_line('%s|%s' % (parent['id'], key), name, values, parent_id=parent['id'],
                                      level=parent['level'] + 1, kind=kind, open_record=open_record))

        if options['statement_type'] == 'activity':
            add('opening', _("Opening balance at %s", self._om_format_date(options['date_from'])),
                {'balance': line['opening']}, 'opening')
            running = line['opening']
            items = self._om_search_fetch(self.env['account.move.line'], self._odr_partner_domain(options) + self._odr_period_domain(options)
                + [('partner_id', '=', partner_id)], DETAIL_FIELDS, order='date, move_name, id')
            for item in items:
                amount = self._odr_convert(item.balance, item.company_id) * self._odr_sign
                running += amount
                charge, payment = self._odr_split(amount)
                add('aml-%s' % item.id, item.move_name or '', {
                    'date': fields.Date.to_string(item.date), 'label': self._odr_label(item),
                    'date_maturity': item.date_maturity and fields.Date.to_string(item.date_maturity),
                    'charge': charge, 'payment': payment, 'balance': running,
                }, 'detail', ('account.move', item.move_id.id))
        else:
            running = 0.0
            for item in data['open_items'].get(partner_id, []):
                running += item['amount']
                charge, payment = self._odr_split(item['amount'])
                values = item['values']
                add('aml-%s' % item['id'], item['name'], {
                    'date': values['date'], 'label': values['label'], 'date_maturity': values['date_maturity'],
                    'charge': charge, 'payment': payment, 'balance': running,
                }, 'detail', ('account.move', item['move_id']))
        add('closing', self._odr_closing_label(options), {'balance': line['values']['balance']}, 'closing')
        if options['ageing']:
            ageing = data['ageing'].get(partner_id, {})
            currency = self._om_currency()
            for key, label in data['buckets']:
                amount = ageing.get(key, 0.0)
                if not currency.is_zero(amount):
                    add('ageing-%s' % key, label, {'balance': amount}, 'opening')
        return self._om_page(rows, offset, limit)

    @api.model
    def _odr_closing_label(self, options):
        return _("Amount due at %s", self._om_format_date(options['date_to']))

    @api.model
    def _odr_bucket_label(self, key, label, first):
        if key == 'not_due':
            return _("Not due yet")
        if key == 'older':
            return _("Overdue more than %s days", first - 1)
        return _("Overdue %s days", label)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    @api.model
    def _om_filter_summary(self, options):
        # the statement goes to the partner: only the period is printed above it
        return [(_("Period"), self._om_subtitle(options))]

    @api.model
    def _om_export_extra(self, options):
        partners = self.env['res.partner'].browse(options['partner_ids'])
        return {'recipient': partners if len(partners) == 1 else False}

    @api.model
    def _odr_statement_attachment(self, options, partner, attach_to_partner):
        title = '%s - %s - %s' % (self._om_report_title(), partner.display_name,
                                  self._om_format_date(options['date_to']))
        return self.env['om.report.export']._om_attachment(
            self._name, {**options, 'partner_ids': [partner.id], 'partner_category_ids': [], 'search': ''},
            name='%s.pdf' % ''.join(c if c.isalnum() or c in ' -_.()' else '-' for c in title),
            res_model='res.partner' if attach_to_partner else False,
            res_id=partner.id if attach_to_partner else False)

    @api.model
    def _om_line_button(self, options, line_id, key):
        partner_id = self._odr_line_id_part(line_id, 'partner')
        partner = self.env['res.partner'].browse(partner_id).exists()
        if not partner:
            return False
        if key == 'download':
            attachment = self._odr_statement_attachment(options, partner, attach_to_partner=False)
            return self.env['om.report.export']._om_download_action(attachment)
        if key == 'email':
            attachment = self._odr_statement_attachment(options, partner, attach_to_partner=True)
            company = self.env.company
            body = Markup(_(
                "<p>Dear %(partner)s,</p><p>Please find attached your statement of account at %(date)s.</p>"
                "<p>Best regards,<br/>%(company)s</p>",
                partner=partner.name, date=self._om_format_date(options['date_to']), company=company.name))
            return {
                'type': 'ir.actions.act_window',
                'name': _("Send the statement"),
                'res_model': 'mail.compose.message',
                'views': [(False, 'form')],
                'target': 'new',
                'context': {
                    'default_model': 'res.partner',
                    'default_res_ids': [partner.id],
                    'default_composition_mode': 'comment',
                    'default_partner_ids': [partner.id],
                    'default_subject': _("%(company)s: statement of account at %(date)s",
                                                  company=company.name,
                                                  date=self._om_format_date(options['date_to'])),
                    'default_body': body,
                    'default_attachment_ids': [(6, 0, attachment.ids)],
                },
            }
        return False


class OmDynamicReportCustomerStatement(models.AbstractModel):
    _name = 'om.dynamic.report.customer.statement'
    _inherit = 'om.dynamic.report.statement'
    _description = 'Dynamic Customer Statement'

    _report_name = 'Customer Statement'
    _report_description = _lt("Statement of account to send to a customer, with what is overdue.")
    _report_sequence = 45
    _report_icon = 'receipt_long'
    _odr_aged_model = 'om.dynamic.report.aged.receivable'
    _odr_sign = 1

    @api.model
    def _om_report_title(self):
        return _("Customer Statement")

    @api.model
    def _odr_charge_label(self):
        return _("Invoiced")

    @api.model
    def _odr_payment_label(self):
        return _("Paid")


class OmDynamicReportVendorStatement(models.AbstractModel):
    _name = 'om.dynamic.report.vendor.statement'
    _inherit = 'om.dynamic.report.statement'
    _description = 'Dynamic Vendor Statement'

    _report_name = 'Vendor Statement'
    _report_description = _lt("What is owed to a vendor, bill by bill, with what is overdue.")
    _report_sequence = 46
    _report_icon = 'request_quote'
    _odr_aged_model = 'om.dynamic.report.aged.payable'
    _odr_sign = -1

    @api.model
    def _om_report_title(self):
        return _("Vendor Statement")

    @api.model
    def _odr_charge_label(self):
        return _("Billed")

    @api.model
    def _odr_payment_label(self):
        return _("Paid")

    @api.model
    def _odr_closing_label(self, options):
        return _("Amount owed at %s", self._om_format_date(options['date_to']))
