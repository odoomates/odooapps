import io
from datetime import date, datetime

import openpyxl

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_account_bank_statement_import.parsers import csv_file


@tagged('post_install', '-at_install')
class TestCsvParser(TransactionCase):

    def _make_map(self, **values):
        return self.env['account.statement.import.map'].create(dict({
            'name': 'Test Map',
            'date_format': '%d/%m/%Y',
            'column_date': 'Date',
            'column_label': 'Label',
            'column_amount': 'Amount',
        }, **values))

    def _parse(self, content, filename, file_map):
        if isinstance(content, str):
            content = content.encode('utf-8')
        return csv_file.parse(content, filename, {'map': file_map._get_map_options(), 'date_format': None})

    # -------------------------------------------------------------------------
    # CSV
    # -------------------------------------------------------------------------
    def test_csv_amount_column(self):
        """ A plain comma separated file with one signed amount column. """
        file_map = self._make_map(column_ref='Reference', column_partner='Partner',
                                  column_currency='Currency', column_unique_id='Id')
        content = (
            'Date,Label,Amount,Reference,Partner,Currency,Id\n'
            '01/02/2024,Coffee shop,-12.50,REF1,Java Ltd,EUR,T1\n'
            '\n'
            '03/02/2024,Salary,1500.00,REF2,Acme,EUR,T2\n'
        )
        statements = self._parse(content, 'bank.csv', file_map)
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement['date'], date(2024, 2, 3), "the date of the last transaction")
        self.assertIsNone(statement['name'])
        self.assertIsNone(statement['balance_start'])
        self.assertIsNone(statement['balance_end_real'])
        self.assertEqual(statement['currency_code'], 'EUR')
        self.assertEqual(len(statement['transactions']), 2, "the empty row is skipped")
        first, second = statement['transactions']
        self.assertEqual(first['date'], date(2024, 2, 1))
        self.assertEqual(first['payment_ref'], 'Coffee shop')
        self.assertEqual(first['amount'], -12.5)
        self.assertEqual(first['ref'], 'REF1')
        self.assertEqual(first['partner_name'], 'Java Ltd')
        self.assertEqual(first['unique_import_id'], 'T1')
        self.assertEqual(second['amount'], 1500.0)
        self.assertEqual(second['unique_import_id'], 'T2')

    def test_csv_debit_and_credit_columns(self):
        """ A file with a debit column and a credit column, the debit written both ways. """
        file_map = self._make_map(column_amount=False, column_debit='Debit', column_credit='Credit')
        content = (
            'Date,Label,Debit,Credit\n'
            '01/02/2024,Rent,800.00,\n'
            '02/02/2024,Client payment,,250.00\n'
        )
        transactions = self._parse(content, 'bank.csv', file_map)[0]['transactions']
        self.assertEqual([line['amount'] for line in transactions], [-800.0, 250.0],
                         "a debit leaves the account")

        negative_map = self._make_map(column_amount=False, column_debit='Debit', column_credit='Credit',
                                      debit_positive=False)
        content = (
            'Date,Label,Debit,Credit\n'
            '01/02/2024,Rent,-800.00,\n'
            '02/02/2024,Client payment,,250.00\n'
        )
        transactions = self._parse(content, 'bank.csv', negative_map)[0]['transactions']
        self.assertEqual([line['amount'] for line in transactions], [-800.0, 250.0],
                         "the debit is already negative in the file")

    def test_csv_comma_decimal_separator(self):
        """ A semicolon separated file with comma decimals and dots grouping the thousands. """
        file_map = self._make_map(delimiter=';', decimal_separator=',', thousands_separator='.',
                                  column_label='Libelle', column_amount='Montant')
        content = (
            'Date;Libelle;Montant\n'
            '15/03/2024;Achat;-1.234,56\n'
            '16/03/2024;Virement;2.000,00\n'
            '17/03/2024;Frais;(12,30)\n'
        )
        transactions = self._parse(content, 'bank.csv', file_map)[0]['transactions']
        self.assertEqual([line['amount'] for line in transactions], [-1234.56, 2000.0, -12.3])

    def test_csv_without_header_by_column_number(self):
        """ A file with no header row, two rows to skip and columns given by their number. """
        file_map = self._make_map(has_header=False, skip_rows=2, column_date='1', column_label='2',
                                  column_amount='3', column_unique_id='4')
        content = (
            'Statement of account 12345\n'
            'Generated on 01/04/2024\n'
            '01/04/2024,Shop,-10.00,ID1\n'
            '02/04/2024,Refund,10.00,ID2\n'
        )
        statement = self._parse(content, 'bank.csv', file_map)[0]
        self.assertEqual(statement['date'], date(2024, 4, 2))
        self.assertEqual([line['payment_ref'] for line in statement['transactions']], ['Shop', 'Refund'])
        self.assertEqual([line['amount'] for line in statement['transactions']], [-10.0, 10.0])
        self.assertEqual([line['unique_import_id'] for line in statement['transactions']], ['ID1', 'ID2'])

    # -------------------------------------------------------------------------
    # Excel
    # -------------------------------------------------------------------------
    def test_xlsx_file(self):
        """ The same map reads an Excel file, where the dates are real dates. """
        file_map = self._make_map(column_ref='Reference')
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = 'Transactions'
        sheet.append(['Date', 'Label', 'Amount', 'Reference'])
        sheet.append([datetime(2024, 5, 6), 'Supplier', -99.99, 'INV1'])
        sheet.append([None, None, None, None])
        sheet.append([datetime(2024, 5, 7), 'Customer', 120.5, 'INV2'])
        stream = io.BytesIO()
        workbook.save(stream)

        statement = self._parse(stream.getvalue(), 'bank.xlsx', file_map)[0]
        self.assertEqual(statement['date'], date(2024, 5, 7))
        self.assertEqual(len(statement['transactions']), 2, "the empty row is skipped")
        self.assertEqual(statement['transactions'][0]['date'], date(2024, 5, 6))
        self.assertEqual(statement['transactions'][0]['amount'], -99.99)
        self.assertEqual(statement['transactions'][1]['payment_ref'], 'Customer')
        self.assertEqual(statement['transactions'][1]['ref'], 'INV2')

    # -------------------------------------------------------------------------
    # Errors
    # -------------------------------------------------------------------------
    def test_bad_date_tells_the_row(self):
        """ A date that does not match the format of the map names the row of the file. """
        file_map = self._make_map()
        content = (
            'Date,Label,Amount\n'
            '01/02/2024,Good row,10.00\n'
            '2024-02-03,Bad row,20.00\n'
        )
        with self.assertRaisesRegex(ValueError, 'Row 3'):
            self._parse(content, 'bank.csv', file_map)

        missing_column = self._make_map(column_amount='Total')
        with self.assertRaisesRegex(ValueError, 'amount column'):
            self._parse(content, 'bank.csv', missing_column)

        bad_amount = self._make_map()
        content = 'Date,Label,Amount\n01/02/2024,Bad amount,ten euros\n'
        with self.assertRaisesRegex(ValueError, 'Row 2'):
            self._parse(content, 'bank.csv', bad_amount)

    def test_other_formats_are_left_to_the_other_parsers(self):
        """ The parser gives back the files of the other formats, and the files without a map. """
        file_map = self._make_map()
        options = {'map': file_map._get_map_options(), 'date_format': None}
        self.assertIsNone(csv_file.parse(b'Date,Label,Amount\n01/02/2024,X,1.00\n', 'bank.csv',
                                         {'map': None}), "no map: the layout is unknown")
        self.assertIsNone(csv_file.parse(b'<?xml version="1.0"?><Document/>', 'bank.xml', options))
        self.assertIsNone(csv_file.parse(b'OFXHEADER:100\nDATA:OFXSGML\n', 'bank.ofx', options))
        self.assertIsNone(csv_file.parse(b'!Type:Bank\nD01/02/2024\nT-10.00\n^\n', 'bank.qif', options))
        self.assertIsNone(csv_file.parse(b':20:STATEMENT\n:25:123456789\n:61:2402010201D10,00N\n',
                                         'bank.sta', options))

    def test_map_needs_an_amount_or_a_debit_and_a_credit(self):
        """ The constraint on the columns of the amount. """
        with self.assertRaises(ValidationError):
            self._make_map(column_amount=False)
        with self.assertRaises(ValidationError):
            self._make_map(column_amount=False, column_debit='Debit')
        with self.assertRaises(ValidationError):
            self._make_map(column_amount=False, column_credit='Credit')
        file_map = self._make_map(column_amount=False, column_debit='Debit', column_credit='Credit')
        self.assertTrue(file_map.id, "a debit column and a credit column are enough")
        with self.assertRaises(ValidationError):
            file_map.write({'column_debit': False})
