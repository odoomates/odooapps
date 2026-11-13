import math
import time

from odoo import api, models, _
from odoo.exceptions import UserError

# The statements the pack is made of, in print order: the flag on the wizard and the
# account.financial.report root it prints. Both roots are defined in
# wizard/balance_sheet.xml, the same records the standalone reports use.
STATEMENTS = (
    ('include_balance_sheet', 'accounting_pdf_reports.account_financial_report_balancesheet0'),
    ('include_profit_and_loss', 'accounting_pdf_reports.account_financial_report_profitandloss0'),
)

# The pack paginates itself rather than letting the statements flow, so the contents
# page can name the page each one starts on. Rows here are single-line (a name and an
# amount), and this is how many fit under the heading of a portrait page.
ROWS_PER_PAGE = 32

# The cover and the contents, which come before the first statement.
FRONT_PAGES = 2


class ReportAnnual(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_annual'
    _description = 'Annual Report'

    @api.model
    def _statement(self, form, xmlid):
        """ One section of the pack, computed by the financial report engine.

        The balances are not recomputed here: this hands the work to
        ``report_financial.get_account_lines``, which is what the standalone Balance
        Sheet and Profit and Loss run. The annual report therefore cannot print
        different numbers from them.
        """
        report = self.env.ref(xmlid, raise_if_not_found=False)
        if not report:
            return None
        lines = self.env['report.accounting_pdf_reports.report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': form.get('used_context') or {},
            # the engine computes the comparison column itself, given a second context
            'comparison_context': form.get('comparison_context') or {},
            'enable_filter': bool(form.get('enable_filter')),
            'debit_credit': False,
        })
        if form.get('enable_filter') and form.get('show_variance'):
            for line in lines:
                line['variance'] = line['balance'] - line.get('balance_cmp', 0.0)
                base = line.get('balance_cmp') or 0.0
                # a movement away from nothing has no meaningful percentage
                line['variance_pct'] = (line['variance'] / abs(base) * 100.0) if base else False
        return {'name': report.name, 'lines': lines}

    @api.model
    def _key_figures(self, form):
        """ The handful of numbers someone looks for first.

        Taken from the same report roots the statements are built from, in a single
        pass of the engine, so they cannot disagree with the pages that follow.
        """
        wanted = (
            (_('Revenue'), 'accounting_pdf_reports.account_financial_report_income0'),
            (_('Expenses'), 'accounting_pdf_reports.account_financial_report_expense0'),
            (_('Result for the period'), 'accounting_pdf_reports.account_financial_report_profitandloss0'),
            (_('Total assets'), 'accounting_pdf_reports.account_financial_report_assets0'),
        )
        reports, labels = self.env['account.financial.report'], {}
        for label, xmlid in wanted:
            report = self.env.ref(xmlid, raise_if_not_found=False)
            if report:
                reports |= report
                labels[report.id] = label
        if not reports:
            return []
        engine = self.env['report.accounting_pdf_reports.report_financial']
        current = engine.with_context(**(form.get('used_context') or {}))._compute_report_balance(reports)
        previous = {}
        if form.get('enable_filter'):
            previous = engine.with_context(
                **(form.get('comparison_context') or {}))._compute_report_balance(reports)
        figures = []
        for report in reports:
            sign = float(report.sign)
            figure = {'label': labels[report.id], 'amount': current[report.id]['balance'] * sign}
            if previous:
                figure['amount_cmp'] = previous[report.id]['balance'] * sign
            figures.append(figure)
        return figures

    @api.model
    def _paginate(self, lines):
        """ Cut a statement into pages, so its length is known before it is printed. """
        printable = [line for line in lines if line.get('level') != 0]
        pages = [printable[i:i + ROWS_PER_PAGE] for i in range(0, len(printable), ROWS_PER_PAGE)]
        return pages or [[]]

    @api.model
    def _merge_cash_flow(self, cash_flow, previous):
        """ Hang last year's figures off this year's cash flow statement.

        The engine drops any line that is zero, so the two periods rarely hold the
        same rows: a line present only last year still has to appear, or its figure
        would vanish from the comparison. Rows are matched on the activity and the
        line key, never on the label, which is translated.
        """
        prior_sections = {section['activity']: section for section in previous['sections']}
        for section in cash_flow['sections']:
            prior = prior_sections.pop(section['activity'], None) or {'lines': [], 'total': 0.0}
            prior_lines = {line['key']: line for line in prior['lines']}
            for line in section['lines']:
                line['amount_cmp'] = prior_lines.pop(line['key'], {}).get('amount', 0.0)
            for line in prior_lines.values():
                section['lines'].append(
                    {**line, 'accounts': [], 'amount': 0.0, 'amount_cmp': line['amount']})
            section['total_cmp'] = prior['total']
        for key in ('opening', 'net_change', 'closing'):
            cash_flow['%s_cmp' % key] = previous[key]
        return cash_flow

    @api.model
    def _cash_flow_pages(self, cash_flow):
        """ How many pages the cash flow statement takes, counting the rows it prints. """
        # opening, net change and closing, then a heading, the lines and a total per section
        rows = 3
        for section in cash_flow['sections']:
            rows += 2 + max(len(section['lines']), 1)
        return max(math.ceil(rows / ROWS_PER_PAGE), 1)

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        form = data['form']

        statements = []
        for flag, xmlid in STATEMENTS:
            if not form.get(flag):
                continue
            statement = self._statement(form, xmlid)
            if statement:
                statements.append(statement)

        cash_flow = None
        if form.get('include_cash_flow'):
            # the reconciliations are read through the ORM, the totals with a grouped
            # query: write the changes first, as the cash flow report itself does
            self.env.flush_all()
            engine = self.env['report.accounting_pdf_reports.report_cash_flow']
            cash_flow = engine._get_cash_flow(form)
            if form.get('enable_filter') and form.get('date_from_cmp'):
                # this engine has no comparison of its own, so it is simply run twice
                previous = engine._get_cash_flow(dict(
                    form, date_from=form['date_from_cmp'], date_to=form['date_to_cmp']))
                cash_flow = self._merge_cash_flow(cash_flow, previous)

        # Walk everything that prints, in order, handing each part the page it starts
        # on. Anything added here has to be counted, or the contents page drifts away
        # from the report.
        contents = []
        page = FRONT_PAGES + 1

        key_figures = self._key_figures(form) if form.get('include_key_figures') else []
        if key_figures:
            contents.append({'name': _('Key Figures'), 'page': page})
            page += 1

        for statement in statements:
            statement['pages'] = self._paginate(statement['lines'])
            contents.append({'name': statement['name'], 'page': page})
            page += len(statement['pages'])
        if cash_flow:
            contents.append({'name': _('Cash Flow Statement'), 'page': page})
            page += self._cash_flow_pages(cash_flow)

        notes = (form.get('notes') or '').strip()
        if notes:
            contents.append({'name': _('Notes to the Financial Statements'), 'page': page})
            page += 1
        if form.get('include_signatures'):
            contents.append({'name': _('Approval'), 'page': page})
            page += 1

        journals = self.env['account.journal'].browse(form.get('journal_ids') or [])
        return {
            'doc_ids': docids,
            'doc_model': 'account.annual.report',
            'data': form,
            'docs': self.env['account.annual.report'].browse(docids),
            'time': time,
            'statements': statements,
            'cash_flow': cash_flow,
            'contents': contents,
            'key_figures': key_figures,
            # laid out two to a row on the page; grouping here keeps the arithmetic
            # out of the template
            'key_figure_rows': [key_figures[i:i + 2] for i in range(0, len(key_figures), 2)],
            'notes': notes,
            'print_journal': journals.mapped('code'),
        }
