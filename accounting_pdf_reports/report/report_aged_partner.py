import time
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportAgedPartnerBalance(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_agedpartnerbalance'
    _description = 'Aged Partner Balance Report'

    def _get_partner_move_lines(self, account_type, partner_ids,
                                date_from, target_move, period_length):
        # This method can receive the context key 'include_nullified_amount' {Boolean}
        # Do an invoice and a payment and unreconcile. The amount will be nullified
        # By default, the partner wouldn't appear in this report.
        # The context key allow it to appear
        # In case of a period_length of 30 days as of 2019-02-08, we want the following periods:
        # Name       Stop         Start
        # 1 - 30   : 2019-02-07 - 2019-01-09
        # 31 - 60  : 2019-01-08 - 2018-12-10
        # 61 - 90  : 2018-12-09 - 2018-11-10
        # 91 - 120 : 2018-11-09 - 2018-10-11
        # +120     : 2018-10-10
        periods = {}
        start = datetime.strptime(str(date_from), "%Y-%m-%d")
        date_from = datetime.strptime(str(date_from), "%Y-%m-%d").date()
        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length)
            period_name = str((5-(i+1)) * period_length + 1) + '-' + str((5-i) * period_length)
            period_stop = (start - relativedelta(days=1)).strftime('%Y-%m-%d')
            if i == 0:
                period_name = '+' + str(4 * period_length)
            periods[str(i)] = {
                'name': period_name,
                'stop': period_stop,
                'start': (i!=0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop

        res = []
        total = []
        cr = self.env.cr
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        # the company of the report (given by the wizard), not the default company of the user
        company = self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company
        user_currency = company.currency_id
        # a branch posts its entries in its own company: they belong to the report
        # of the parent that consolidates it
        company_ids = self.env.context.get('company_ids') or self.env['res.company'].search(
            [('id', 'child_of', company.id)]).ids
        move_state = ['draft', 'posted']
        date = self.env.context.get('date') or fields.Date.context_today(self)

        if target_move == 'posted':
            move_state = ['posted']
        # the open items as of the date: the items not reconciled yet, and the ones reconciled after it
        reconciliation_clause = '''(l.reconciled IS FALSE
            OR EXISTS(SELECT 1 FROM account_partial_reconcile p
                       WHERE p.debit_move_id = l.id AND p.max_date > %(date_from)s)
            OR EXISTS(SELECT 1 FROM account_partial_reconcile p
                       WHERE p.credit_move_id = l.id AND p.max_date > %(date_from)s))'''
        args = {
            'move_state': tuple(move_state),
            'account_type': tuple(account_type),
            'date_from': date_from,
            'company_ids': tuple(company_ids),
        }
        query = ('''
            SELECT DISTINCT l.partner_id, UPPER(res_partner.name)
            FROM account_move_line AS l left join res_partner on l.partner_id = res_partner.id, '''
                 '''account_account, account_move am
            WHERE (l.account_id = account_account.id)
                AND (l.move_id = am.id)
                AND (am.state IN %(move_state)s)
                AND (account_account.account_type IN %(account_type)s)
                AND ''' + reconciliation_clause + '''
                AND (l.date <= %(date_from)s)
                AND l.company_id IN %(company_ids)s
            ORDER BY UPPER(res_partner.name)''')
        cr.execute(query, args)
        partners = cr.dictfetchall()
        # put a total of 0
        for i in range(7):
            total.append(0)

        # Build a string like (1,2,3) for easy use in SQL query
        if not partner_ids:
            partner_ids = [partner['partner_id'] for partner in partners if partner['partner_id']]
        lines = dict((partner['partner_id'] or False, []) for partner in partners)
        if not partner_ids:
            return [], [], {}
        args['partner_ids'] = tuple(partner_ids)

        # the period of each item: 6 when it is not due yet, else 1 to 5 for the
        # periods '0' (the oldest) to '4' (the most recent)
        period_cases = ['WHEN COALESCE(l.date_maturity, l.date) >= %(date_from)s THEN 6']
        for i in range(5):
            start, stop = periods[str(i)]['start'], periods[str(i)]['stop']
            args.update({f'start_{i}': start, f'stop_{i}': stop})
            if start and stop:
                condition = f'COALESCE(l.date_maturity, l.date) BETWEEN %(start_{i})s AND %(stop_{i})s'
            elif start:
                condition = f'COALESCE(l.date_maturity, l.date) >= %(start_{i})s'
            else:
                condition = f'COALESCE(l.date_maturity, l.date) <= %(stop_{i})s'
            period_cases.append(f'WHEN {condition} THEN {i + 1}')

        # the open items with what was reconciled with them until the date, in one query: an item
        # reconciled before the date and not after is settled, and left out
        query = '''
            SELECT l.id, l.partner_id, l.company_id, l.balance,
                   CASE ''' + ' '.join(period_cases) + ''' END AS period,
                   (SELECT COALESCE(SUM(p.amount), 0) FROM account_partial_reconcile p
                     WHERE p.credit_move_id = l.id AND p.max_date <= %(date_from)s) AS matched_debit,
                   (SELECT COALESCE(SUM(p.amount), 0) FROM account_partial_reconcile p
                     WHERE p.debit_move_id = l.id AND p.max_date <= %(date_from)s) AS matched_credit
            FROM account_move_line AS l, account_account, account_move am
            WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                AND (am.state IN %(move_state)s)
                AND (account_account.account_type IN %(account_type)s)
                AND ((l.partner_id IN %(partner_ids)s) OR (l.partner_id IS NULL))
                AND ''' + reconciliation_clause + '''
                AND (l.date <= %(date_from)s)
                AND l.company_id IN %(company_ids)s'''
        cr.execute(query, args)

        # This dictionary will store the not due amount of all partners
        undue_amounts = {}
        # Each history will contain: history[1] = {'<partner_id>': <partner_debit-credit>}
        history = [{} for i in range(5)]
        MoveLine = self.env['account.move.line']
        Company = self.env['res.company']
        for row in cr.dictfetchall():
            partner_id = row['partner_id'] or False
            line_currency = Company.browse(row['company_id']).currency_id
            line_amount = line_currency._convert(row['balance'], user_currency, company, date)
            if user_currency.is_zero(line_amount):
                continue
            # the amounts reconciled with an item are in the currency of its company
            if row['matched_debit']:
                line_amount += line_currency._convert(row['matched_debit'], user_currency, company, date)
            if row['matched_credit']:
                line_amount -= line_currency._convert(row['matched_credit'], user_currency, company, date)
            if user_currency.is_zero(line_amount):
                continue
            amounts = undue_amounts if row['period'] == 6 else history[row['period'] - 1]
            amounts[partner_id] = amounts.get(partner_id, 0.0) + line_amount
            lines.setdefault(partner_id, []).append({
                'line': MoveLine.browse(row['id']),
                'amount': line_amount,
                'period': row['period'],
            })

        # the names of the partners are read together, not one partner at a time
        partner_records = self.env['res.partner'].browse(
            [partner['partner_id'] for partner in partners if partner['partner_id']])
        for partner in partners:
            if partner['partner_id'] is None:
                partner['partner_id'] = False
            at_least_one_amount = False
            values = {}
            undue_amt = 0.0
            if partner['partner_id'] in undue_amounts:  # Making sure this partner actually was found by the query
                undue_amt = undue_amounts[partner['partner_id']]

            total[6] = total[6] + undue_amt
            values['direction'] = undue_amt
            if not float_is_zero(values['direction'], precision_rounding=user_currency.rounding):
                at_least_one_amount = True

            for i in range(5):
                during = False
                if partner['partner_id'] in history[i]:
                    during = [history[i][partner['partner_id']]]
                # Adding counter
                total[(i)] = total[(i)] + (during and during[0] or 0)
                values[str(i)] = during and during[0] or 0.0
                if not float_is_zero(values[str(i)],
                                     precision_rounding=user_currency.rounding):
                    at_least_one_amount = True
            values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
            ## Add for total
            total[(i + 1)] += values['total']
            values['partner_id'] = partner['partner_id']
            if partner['partner_id']:
                browsed_partner = partner_records.browse(partner['partner_id']).with_prefetch(partner_records._ids)
                values['name'] = browsed_partner.name and len(
                    browsed_partner.name) >= 45 and browsed_partner.name[
                                                    0:40] + '...' or browsed_partner.name
                values['trust'] = browsed_partner.trust
            else:
                values['name'] = _('Unknown Partner')
                values['trust'] = False

            if at_least_one_amount or (self.env.context.get('include_nullified_amount')
                                       and lines[partner['partner_id']]):
                res.append(values)

        return res, total, lines

    @api.model
    def _get_form_company_id(self, form):
        company = form.get('company_id')
        return company[0] if isinstance(company, (list, tuple)) else company or self.env.company.id

    @api.model
    def _get_report_values(self, docids, data=None):
        if (not data.get('form') or not self.env.context.get('active_model')
                or self.env.context.get('active_id') is None):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))

        target_move = data['form'].get('target_move', 'all')
        date_from = data['form'].get('date_from') or fields.Date.context_today(self)

        if data['form']['result_selection'] == 'customer':
            account_type = ['asset_receivable']
        elif data['form']['result_selection'] == 'supplier':
            account_type = ['liability_payable']
        else:
            account_type = ['asset_receivable', 'liability_payable']
        partner_ids = data['form']['partner_ids']
        movelines, total, dummy = self.with_context(
            company_id=self._get_form_company_id(data['form'])
        )._get_partner_move_lines(
            account_type, partner_ids, date_from, target_move, data['form']['period_length']
        )
        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_partner_lines': movelines,
            'get_direction': total,
        }
