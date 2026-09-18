import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.base.models.res_partner_bank import sanitize_account_number

from ..parsers import camt, csv_file, mt940, ofx, qif

_logger = logging.getLogger(__name__)


class AccountStatementImport(models.TransientModel):
    _name = 'account.statement.import'
    _description = 'Import Bank Statement'

    attachment_ids = fields.Many2many(
        'ir.attachment', string='Files', required=True,
        help="The statement files of your bank: CAMT.053, MT940, OFX, QFX, QIF, CSV or Excel.")
    journal_id = fields.Many2one(
        'account.journal', string='Journal', check_company=True, domain="[('type', 'in', ('bank', 'cash'))]",
        help="Leave empty to use the journal of the bank account written in the file.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    map_id = fields.Many2one(
        'account.statement.import.map', string='File Map', check_company=True,
        compute='_compute_map_id', store=True, readonly=False,
        help="The columns of the CSV or Excel files of your bank. Not needed for the other formats.")
    date_format = fields.Char(
        string='Date Format',
        help="The format of the dates of a QIF file, such as %d/%m/%Y. Left empty, the day and the month are "
             "told apart from the values themselves.")

    @api.depends('journal_id')
    def _compute_map_id(self):
        for wizard in self:
            wizard.map_id = wizard.journal_id.statement_import_map_id

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------

    def _get_parsers(self):
        """ :return: the parsers of the statement files, in the order they are tried. A module adding a format
        overrides this method. """
        return [camt.parse, ofx.parse, mt940.parse, qif.parse, csv_file.parse]

    def _parse_file(self, data, filename):
        """ :return: the statements of the file, read by the first parser that recognises it """
        options = {
            'map': self.map_id._get_map_options() if self.map_id else None,
            'date_format': self.date_format or None,
        }
        errors = []
        for parser in self._get_parsers():
            try:
                statements = parser(data, filename, options)
            except ValueError as error:
                errors.append(str(error))
                continue
            except Exception as error:  # a parser must not break the import of the other files
                _logger.warning("The parser %s failed on %s: %s", parser.__module__, filename, error)
                errors.append(str(error))
                continue
            if statements is not None:
                return statements
        message = _('The format of the file %s is not supported.', filename)
        if errors:
            message += '\n\n' + '\n'.join(errors)
        raise UserError(message)

    # -------------------------------------------------------------------------
    # Import
    # -------------------------------------------------------------------------

    def _find_journal(self, statement, filename):
        """ :return: the journal of a statement: the one of the wizard, or the one of the bank account of the file """
        account_number = (statement.get('account_number') or '').replace(' ', '')
        journal = self.journal_id
        if account_number:
            sanitized = sanitize_account_number(account_number)
            matching = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', 'in', self.env.companies.ids),
                ('bank_account_id.sanitized_account_number', '=', sanitized),
            ], limit=1)
            if matching and journal and matching != journal:
                raise UserError(_(
                    'The file %(file)s is the statement of the account %(account)s, which belongs to the journal '
                    '%(journal)s, not to %(chosen)s.',
                    file=filename, account=account_number, journal=matching.display_name,
                    chosen=journal.display_name,
                ))
            journal = matching or journal
        if not journal:
            raise UserError(_(
                'No journal was found for the account %(account)s of the file %(file)s. Choose a journal, or '
                'write that account number on the bank account of its journal.',
                account=account_number or _('of the file'), file=filename,
            ))
        if journal.type not in ('bank', 'cash'):
            raise UserError(_('A statement is imported in a bank or cash journal, not in %s.', journal.display_name))
        return journal

    def _check_currency(self, statement, journal, filename):
        currency_code = (statement.get('currency_code') or '').upper()
        if not currency_code:
            return
        journal_currency = journal.currency_id or journal.company_id.currency_id
        if currency_code != journal_currency.name.upper():
            raise UserError(_(
                'The file %(file)s is in %(file_currency)s, but the journal %(journal)s is in %(currency)s.',
                file=filename, file_currency=currency_code, journal=journal.display_name,
                currency=journal_currency.name,
            ))

    def _statement_line_values(self, transaction, journal, statement):
        unique_import_id = transaction.get('unique_import_id')
        if unique_import_id:
            # the same transaction file may be imported in two journals of two companies
            unique_import_id = f'{journal.id}-{unique_import_id}'
        narration = transaction.get('narration')
        return {
            'journal_id': journal.id,
            'date': transaction['date'],
            'payment_ref': transaction['payment_ref'],
            'amount': transaction['amount'],
            'unique_import_id': unique_import_id,
            'partner_name': transaction.get('partner_name'),
            'account_number': transaction.get('account_number'),
            'transaction_type': transaction.get('transaction_type'),
            'narration': narration,
            'transaction_details': {
                key: value for key, value in (
                    ('reference', transaction.get('ref')),
                    ('narration', narration),
                    ('import_id', transaction.get('unique_import_id')),
                ) if value
            },
        }

    def _import_statement(self, statement, filename, attachment):
        """ Create the statement of one account of one file, without the transactions already imported.

        :return: (the statement created or an empty recordset, the number of transactions left out)
        """
        journal = self._find_journal(statement, filename)
        self._check_currency(statement, journal, filename)
        transactions = statement.get('transactions') or []
        if not transactions:
            return self.env['account.bank.statement'], 0

        values = [self._statement_line_values(transaction, journal, statement) for transaction in transactions]
        import_ids = [line['unique_import_id'] for line in values if line['unique_import_id']]
        already_imported = set(self.env['account.bank.statement.line'].sudo().search_fetch(
            [('unique_import_id', 'in', import_ids)], ['unique_import_id'],
        ).mapped('unique_import_id')) if import_ids else set()
        new_values = [line for line in values
                      if not line['unique_import_id'] or line['unique_import_id'] not in already_imported]
        skipped = len(values) - len(new_values)
        if not new_values:
            return self.env['account.bank.statement'], skipped

        created = self.env['account.bank.statement'].create({
            'name': statement.get('name') or filename,
            'reference': filename,
            'line_ids': [(0, 0, line) for line in new_values],
            **({'date': statement['date']} if statement.get('date') else {}),
            **({'balance_start': statement['balance_start']} if statement.get('balance_start') is not None else {}),
            **({'balance_end_real': statement['balance_end_real']}
               if statement.get('balance_end_real') is not None else {}),
        })
        attachment.copy({'res_model': 'account.bank.statement', 'res_id': created.id})
        return created, skipped

    def action_import(self):
        self.ensure_one()
        statements = self.env['account.bank.statement']
        skipped = 0
        for attachment in self.attachment_ids:
            filename = attachment.name or ''
            # the content of an attachment is a lazy binary value
            raw = attachment.raw
            data = bytes(getattr(raw, 'content', raw) or b'')
            for statement in self._parse_file(data, filename):
                created, left_out = self._import_statement(statement, filename, attachment)
                statements |= created
                skipped += left_out
        if not statements:
            raise UserError(_(
                'Every transaction of %(count)s file(s) was already imported.', count=len(self.attachment_ids),
            ) if skipped else _('No transaction was found in the file(s).'))

        action = self.env['ir.actions.act_window']._for_xml_id('account.action_bank_statement_tree')
        action['domain'] = [('id', 'in', statements.ids)]
        action['context'] = {'create': False}
        if skipped:
            message = _('%(imported)s transaction(s) imported, %(skipped)s already there.',
                        imported=len(statements.line_ids), skipped=skipped)
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'type': 'info', 'message': message,
            })
        return action
