import time
from odoo import api, models, _
from odoo.exceptions import UserError


# the amounts the report sums, as the template asks for them
SUMMED_FIELDS = ('debit', 'credit', 'debit - credit')
# the template asks for the lines partner by partner: they are read for this many partners at once
LINES_BATCH = 500


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_partnerledger'
    _description = 'Partner Ledger Report'

    def _lines(self, data, partner):
        return self._lines_by_partner(data, partner.ids)[partner.id]

    def _lines_by_partner(self, data, partner_ids):
        """ The journal items of the partners, by partner, in one query """
        full_account = {partner_id: [] for partner_id in partner_ids}
        if not partner_ids:
            return full_account
        currency = self.env['res.currency']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        lang_code = self.env.context.get('lang') or 'en_US'
        params = ([lang_code, tuple(partner_ids), tuple(data['computed']['move_state']),
                   tuple(data['computed']['account_ids'])] + query_get_data[2])
        query = ("""
            SELECT "account_move_line".id, "account_move_line".partner_id, "account_move_line".date, j.code, COALESCE(acc.name->>%s, acc.name->>'en_US') as a_name, """
                 '''"account_move_line".ref, m.name as move_name, "account_move_line".name, '''
                 '''"account_move_line".debit, "account_move_line".credit, "account_move_line".amount_currency,'''
                 '''"account_move_line".currency_id, c.symbol AS currency_code
            FROM ''' + query_get_data[0] + """
            LEFT JOIN account_journal j ON ("account_move_line".journal_id = j.id)
            LEFT JOIN account_account acc ON ("account_move_line".account_id = acc.id)
            LEFT JOIN res_currency c ON ("account_move_line".currency_id=c.id)
            LEFT JOIN account_move m ON (m.id="account_move_line".move_id)
            WHERE "account_move_line".partner_id IN %s
                AND m.state IN %s
                AND "account_move_line".account_id IN %s AND """ + query_get_data[1] + reconcile_clause + """
                ORDER BY "account_move_line".date, "account_move_line".move_id, "account_move_line".id""")
        self.env.cr.execute(query, tuple(params))
        progress = dict.fromkeys(partner_ids, 0.0)
        for r in self.env.cr.dictfetchall():
            partner_id = r.pop('partner_id')
            # move name, reference and label often repeat each other - the label
            # frequently ends with the move name - so anything a part already says is
            # dropped rather than printed twice
            parts = []
            for field_name in ('move_name', 'ref', 'name'):
                value = (r[field_name] or '').strip()
                if value in ('', '/') or any(value in kept for kept in parts):
                    continue
                parts = [kept for kept in parts if kept not in value]
                parts.append(value)
            r['displayed_name'] = ' - '.join(parts)
            progress[partner_id] += r['debit'] - r['credit']
            r['progress'] = progress[partner_id]
            r['currency_id'] = currency.browse(r.get('currency_id'))
            full_account[partner_id].append(r)
        return full_account

    def _sum_partner(self, data, partner, field):
        if field not in SUMMED_FIELDS:
            return
        return self._sum_by_partner(data, partner.ids)[partner.id][field]

    def _sum_by_partner(self, data, partner_ids):
        """ The debit, the credit and the balance of the partners, in one query """
        result = {partner_id: dict.fromkeys(SUMMED_FIELDS, 0.0) for partner_id in partner_ids}
        if not partner_ids:
            return result
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '

        params = ([tuple(partner_ids), tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])]
                  + query_get_data[2])
        # the columns are qualified: the domain may join a table holding the same ones,
        # which PostgreSQL then refuses as an ambiguous reference
        query = """SELECT "account_move_line".partner_id,
                    COALESCE(sum("account_move_line".debit), 0),
                    COALESCE(sum("account_move_line".credit), 0),
                    COALESCE(sum("account_move_line".debit - "account_move_line".credit), 0)
                FROM """ + query_get_data[0] + """, account_move AS m
                WHERE "account_move_line".partner_id IN %s
                    AND m.id = "account_move_line".move_id
                    AND m.state IN %s
                    AND "account_move_line".account_id IN %s
                    AND """ + query_get_data[1] + reconcile_clause + """
                GROUP BY "account_move_line".partner_id"""
        self.env.cr.execute(query, tuple(params))
        for partner_id, debit, credit, balance in self.env.cr.fetchall():
            result[partner_id] = {'debit': debit, 'credit': credit, 'debit - credit': balance}
        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        data['computed'] = {}

        obj_partner = self.env['res.partner']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        data['computed']['move_state'] = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            data['computed']['move_state'] = ['posted']
        result_selection = data['form'].get('result_selection', 'customer')
        if result_selection == 'supplier':
            data['computed']['ACCOUNT_TYPE'] = ['liability_payable']
        elif result_selection == 'customer':
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable']
        else:
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable', 'liability_payable']

        self.env.cr.execute("""
            SELECT a.id
            FROM account_account a
            WHERE a.account_type IN %s
            AND a.active""", (tuple(data['computed']['ACCOUNT_TYPE']),))
        data['computed']['account_ids'] = [a for (a,) in self.env.cr.fetchall()]
        params = [tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        query = """
            SELECT DISTINCT "account_move_line".partner_id
            FROM """ + query_get_data[0] + """, account_account AS account, account_move AS am
            WHERE "account_move_line".partner_id IS NOT NULL
                AND "account_move_line".account_id = account.id
                AND am.id = "account_move_line".move_id
                AND am.state IN %s
                AND "account_move_line".account_id IN %s
                AND account.active
                AND """ + query_get_data[1] + reconcile_clause
        self.env.cr.execute(query, tuple(params))
        if data['form']['partner_ids']:
            partner_ids = data['form']['partner_ids']
        else:
            partner_ids = [res['partner_id'] for res in
                           self.env.cr.dictfetchall()]
        partners = obj_partner.browse(partner_ids)
        partners = sorted(partners, key=lambda x: (x.ref or '', x.name or ''))

        # the template asks for the amounts and the lines of each partner: they are read
        # beforehand, in a few queries instead of a few for each partner
        sums = self._sum_by_partner(data, [partner.id for partner in partners])
        position = {partner.id: index for index, partner in enumerate(partners)}
        batch = {}

        def lines(data, partner):
            if partner.id not in batch:
                start = position.get(partner.id)
                if start is None:
                    return self._lines(data, partner)
                batch.clear()
                batch.update(self._lines_by_partner(
                    data, [p.id for p in partners[start:start + LINES_BATCH]]))
            return batch.pop(partner.id)

        def sum_partner(data, partner, field):
            if field not in SUMMED_FIELDS:
                return
            if partner.id not in sums:
                return self._sum_partner(data, partner, field)
            return sums[partner.id][field]

        return {
            'doc_ids': partner_ids,
            'doc_model': self.env['res.partner'],
            'data': data,
            'docs': partners,
            'time': time,
            'lines': lines,
            'sum_partner': sum_partner,
        }
