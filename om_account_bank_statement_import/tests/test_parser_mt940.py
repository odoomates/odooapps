from datetime import date

from odoo.addons.om_account_bank_statement_import.parsers import mt940
from odoo.tests import TransactionCase, tagged

MT940 = """:20:STARTUMS
:25:NL02ABNA0123456789 EUR
:28C:123/1
:60F:C230101EUR1000,00
:61:2301150115C250,50NTRFNONREF//BANKREF001
:86:/EREF/INV-2023-0001/NAME/ACME Corp/IBAN/NL91ABNA0417164300/REMI/Invoice 2023 0001
:61:2301200120D100,00NTRFCUSTREF002//BANKREF002
:86:/NAME/Electricity Ltd/REMI/Energy bill
:62F:C230131EUR1150,50
"""

MT940_REVERSAL = """:20:REVERSALS
:25:NL02ABNA0123456789
:28C:5
:60F:C230201EUR500,00
:61:2302100210RC75,00NTRFRETURNED//BREF1
:86:/RTRN/MS03/NAME/ACME Corp/REMI/Returned credit transfer
:61:2302110211RD25,00NTRFRETURNED2//BREF2
:86:Returned direct debit
:62F:C230228EUR450,00
"""

MT940_SUBFIELDS = """:20:DE0001
:25:DE89370400440532013000 EUR
:28C:4/1
:60F:C230301EUR2000,00
:61:2303050305D150,00NMSCNONREF//9876543
:86:166?00SEPA-UEBERWEISUNG?20SVWZ+Rechnung 4711?21Kd-Nr 12345?30COBADEFFXXX\
?31DE02120300000000202051?32Muster GmbH?33 & Co KG
:62F:D230331EUR1850,00
"""

MT940_ENVELOPE = """{1:F01ABNANL2AXXXX0000000000}{2:I940ABNANL2AXXXXN}{4:
:20:FREETEXT
:25:BE68539007547034 EUR
:28:7
:60F:C230401EUR100,00
:61:2304020402C50,00NTRFNONREF
:86:Cash deposit main branch
:61:2304020402C50,00NTRFNONREF
:86:Cash deposit main branch
:62F:C230402EUR200,00
-}"""


@tagged('post_install', '-at_install')
class TestMt940Parser(TransactionCase):

    def test_mt940_statement(self):
        """The header tags of a statement, its balances and the number of its lines."""
        statements = mt940.parse(MT940.encode(), 'statement.sta', {})
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement['name'], '123/1')
        self.assertEqual(statement['account_number'], 'NL02ABNA0123456789')
        self.assertEqual(statement['currency_code'], 'EUR')
        self.assertEqual(statement['balance_start'], 1000.0)
        self.assertEqual(statement['balance_end_real'], 1150.50)
        self.assertEqual(statement['date'], date(2023, 1, 31))
        self.assertEqual(len(statement['transactions']), 2)

    def test_mt940_transactions(self):
        """The signs of a credit and of a debit, and the structured information of their lines."""
        credit, debit = mt940.parse(MT940.encode(), 'statement.sta', {})[0]['transactions']
        self.assertEqual(credit['amount'], 250.50)
        self.assertEqual(credit['date'], date(2023, 1, 15))  # the entry date, not the value date
        self.assertEqual(credit['partner_name'], 'ACME Corp')
        self.assertEqual(credit['account_number'], 'NL91ABNA0417164300')
        self.assertEqual(credit['payment_ref'], 'Invoice 2023 0001')
        self.assertEqual(credit['unique_import_id'], 'BANKREF001-123/1-1')
        self.assertEqual(credit['transaction_type'], 'NTRF')
        self.assertTrue(credit['narration'].startswith('/EREF/'))
        self.assertEqual(debit['amount'], -100.0)
        self.assertEqual(debit['date'], date(2023, 1, 20))
        self.assertEqual(debit['partner_name'], 'Electricity Ltd')
        self.assertEqual(debit['payment_ref'], 'Energy bill')
        self.assertEqual(debit['unique_import_id'], 'BANKREF002-123/1-2')

    def test_mt940_reversals(self):
        """RC and RD cancel a credit and a debit, their amounts go the other way."""
        statement = mt940.parse(MT940_REVERSAL.encode(), 'reversal.sta', {})[0]
        reversed_credit, reversed_debit = statement['transactions']
        self.assertEqual(reversed_credit['amount'], -75.0)
        self.assertEqual(reversed_debit['amount'], 25.0)
        self.assertEqual(reversed_credit['partner_name'], 'ACME Corp')
        self.assertEqual(statement['balance_start'] + sum(line['amount'] for line in statement['transactions']),
                         statement['balance_end_real'])

    def test_mt940_subfields(self):
        """The ``?20`` subfields of the German banks, and a debit closing balance."""
        statement = mt940.parse(MT940_SUBFIELDS.encode(), 'umsatz.sta', {})[0]
        self.assertEqual(statement['account_number'], 'DE89370400440532013000')
        self.assertEqual(statement['balance_end_real'], -1850.0)
        transaction = statement['transactions'][0]
        self.assertEqual(transaction['amount'], -150.0)
        self.assertEqual(transaction['partner_name'], 'Muster GmbH & Co KG')
        self.assertEqual(transaction['account_number'], 'DE02120300000000202051')
        self.assertEqual(transaction['payment_ref'], 'SVWZ+Rechnung 4711 Kd-Nr 12345')
        self.assertEqual(transaction['unique_import_id'], '9876543-4/1-1')

    def test_mt940_envelope_and_duplicates(self):
        """A file in its SWIFT envelope, whose two identical lines keep two identifiers."""
        statement = mt940.parse(MT940_ENVELOPE.encode(), 'swift.txt', {})[0]
        self.assertEqual(statement['name'], '7')
        self.assertEqual(len(statement['transactions']), 2)
        first, second = statement['transactions']
        self.assertEqual(first['amount'], second['amount'])
        self.assertEqual(first['date'], second['date'])
        self.assertNotEqual(first['unique_import_id'], second['unique_import_id'])
        self.assertEqual(first['payment_ref'], 'Cash deposit main branch')

    def test_other_formats(self):
        """A file that is not an MT940 is left to the next parser."""
        self.assertIsNone(mt940.parse(b'OFXHEADER:100\nDATA:OFXSGML\n', 'file.ofx', {}))
        self.assertIsNone(mt940.parse(b'<?xml version="1.0"?><Document/>', 'file.xml', {}))
        self.assertIsNone(mt940.parse(b'!Type:Bank\nD01/15/2023\nT250.50\n^\n', 'file.qif', {}))
