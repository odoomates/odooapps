from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountStatementImportMap(models.Model):
    """ The layout of the CSV or Excel files of one bank: the encoding, the separators, the format of the
    dates and the columns to read. The map is kept and reused at every import of that bank. """
    _name = 'account.statement.import.map'
    _description = 'Bank Statement File Map'
    _order = 'name'

    name = fields.Char(string='Name', required=True, help='e.g. My Bank - CSV export')
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company,
        help='Leave empty to share the map with every company.')
    note = fields.Text(string='Notes')

    # -------------------------------------------------------------------------
    # Layout of the file
    # -------------------------------------------------------------------------
    file_encoding = fields.Char(
        string='Encoding', required=True, default='utf-8',
        help='The encoding of the text of the file: utf-8, utf-8-sig, latin1, cp1252... CSV only.')
    delimiter = fields.Char(
        string='Delimiter', required=True, default=',',
        help='The character between two columns, CSV only. Write tab for a tabulation (TSV files).')
    quotechar = fields.Char(
        string='Text Delimiter', default='"', size=1,
        help='The character around a value containing the delimiter. CSV only.')
    decimal_separator = fields.Selection(
        [('.', 'Dot (1234.56)'), (',', 'Comma (1234,56)')],
        string='Decimal Separator', required=True, default='.')
    thousands_separator = fields.Char(
        string='Thousands Separator',
        help="The character grouping the digits of the big numbers, if any: 1,234.56 or 1.234,56 or 1 234,56.")
    date_format = fields.Char(
        string='Date Format', required=True, default='%d/%m/%Y',
        help='The format of the dates of the file, in the Python notation: %d/%m/%Y, %m/%d/%y, %Y-%m-%d...')
    skip_rows = fields.Integer(
        string='Rows to Skip', default=0,
        help='The number of rows to ignore at the top of the file, before the header.')
    has_header = fields.Boolean(
        string='Has a Header Row', default=True,
        help='The first row read holds the names of the columns. Without a header, the columns below are '
             'given by their number, the first column being 1.')
    sheet = fields.Char(
        string='Sheet',
        help='The name or the number (1 for the first one) of the sheet to read. Excel only, the first sheet '
             'by default.')
    debit_positive = fields.Boolean(
        string='Debit is Positive', default=True,
        help='The debit column holds the money leaving the account as a positive number. Uncheck it when '
             'your bank writes the debits with a minus sign.')

    # -------------------------------------------------------------------------
    # Columns: a header name, or the number of the column (the first one being 1)
    # -------------------------------------------------------------------------
    column_date = fields.Char(string='Date Column', required=True, default='Date')
    column_label = fields.Char(string='Label Column', help='The description of the transaction.')
    column_amount = fields.Char(
        string='Amount Column',
        help='One column with the sign of the transaction, negative when the money leaves the account.')
    column_debit = fields.Char(string='Debit Column', help='The money leaving the account.')
    column_credit = fields.Char(string='Credit Column', help='The money entering the account.')
    column_ref = fields.Char(string='Reference Column')
    column_partner = fields.Char(string='Partner Column')
    column_account_number = fields.Char(
        string='Account Number Column', help='The bank account of the other party of the transaction.')
    column_currency = fields.Char(string='Currency Column', help='The ISO code of the currency, e.g. EUR.')
    column_unique_id = fields.Char(
        string='Unique ID Column',
        help='The identifier of the transaction at the bank, to import the same file twice without '
             'duplicating its transactions.')
    column_narration = fields.Char(string='Notes Column')

    @api.constrains('column_amount', 'column_debit', 'column_credit')
    def _check_amount_columns(self):
        for file_map in self:
            if not file_map.column_amount and not (file_map.column_debit and file_map.column_credit):
                raise ValidationError(_(
                    'The map "%s" needs an amount column, or a debit column and a credit column.',
                    file_map.name))

    def _get_map_options(self):
        """ :return: the map as a plain dict, for the parsers, which do not import Odoo """
        self.ensure_one()
        return {
            'name': self.name,
            'encoding': self.file_encoding or 'utf-8',
            'delimiter': self.delimiter or ',',
            'quotechar': self.quotechar or '"',
            'decimal_separator': self.decimal_separator or '.',
            'thousands_separator': self.thousands_separator or '',
            'date_format': self.date_format,
            'skip_rows': self.skip_rows or 0,
            'has_header': self.has_header,
            'sheet': self.sheet or '',
            'debit_positive': self.debit_positive,
            'columns': {
                'date': self.column_date or '',
                'label': self.column_label or '',
                'amount': self.column_amount or '',
                'debit': self.column_debit or '',
                'credit': self.column_credit or '',
                'ref': self.column_ref or '',
                'partner': self.column_partner or '',
                'account_number': self.column_account_number or '',
                'currency': self.column_currency or '',
                'unique_id': self.column_unique_id or '',
                'narration': self.column_narration or '',
            },
        }
