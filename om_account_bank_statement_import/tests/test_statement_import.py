from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

QIF_FILE = """!Type:Bank
D01/02/2026
T-100.50
PSupermarket
MGroceries of the week
^
D15/02/2026
T2500.00
PCustomer payment
N0001
^
"""

OFX_FILE = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>USD
<BANKACCTFROM><BANKID>123456<ACCTID>987654321<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260201<DTEND>20260228
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260203<TRNAMT>-45.20<FITID>OFX-1<NAME>Coffee Shop<MEMO>Card payment</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260210<TRNAMT>1200.00<FITID>OFX-2<NAME>Salary</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>3154.80<DTASOF>20260228</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


@tagged('post_install', '-at_install')
class TestStatementImport(AccountTestInvoicingCommon):

    @classmethod
    def setup_other_currency(cls, code, rates=None):
        """ setup_other_currency() of Odoo 17 and later """
        rates = rates or [('1900-01-01', 1.0), ('2016-01-01', 3.0), ('2017-01-01', 2.0)]
        currency = cls.env['res.currency'].with_context(active_test=False).search([('name', '=', code)], limit=1)
        currency.rate_ids.unlink()
        currency.write({'active': True, 'rate_ids': [Command.create(
            {'name': rate_date, 'rate': rate, 'company_id': cls.env.company.id}) for rate_date, rate in rates]})
        return currency

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data['default_journal_bank']
        cls.journal.bank_account_id = cls.env['res.partner.bank'].create({
            'acc_number': '987654321',
            'partner_id': cls.env.company.partner_id.id,
        })

    def _import(self, content, filename, **values):
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'raw': content.encode() if isinstance(content, str) else content,
        })
        wizard = self.env['account.statement.import'].create({
            'attachment_ids': [Command.set(attachment.ids)], **values,
        })
        return wizard.action_import()

    def _statements_of(self, action):
        return self.env['account.bank.statement'].search(action['domain'])

    def test_import_qif(self):
        action = self._import(QIF_FILE, 'statement.qif',
                              journal_id=self.journal.id, date_format='%d/%m/%Y')
        statement = self._statements_of(action)
        self.assertEqual(len(statement), 1)
        self.assertEqual(statement.journal_id, self.journal)
        self.assertEqual(statement.reference, 'statement.qif')
        lines = statement.line_ids.sorted('date')
        self.assertEqual(lines.mapped('amount'), [-100.5, 2500.0])
        self.assertEqual(lines.mapped('payment_ref'), ['Supermarket', 'Customer payment'])
        self.assertEqual(str(lines[0].date), '2026-02-01')
        self.assertEqual(str(lines[1].date), '2026-02-15')
        self.assertTrue(all(lines.mapped('unique_import_id')))
        # the file stays attached to the statement
        self.assertTrue(self.env['ir.attachment'].search_count([
            ('res_model', '=', 'account.bank.statement'), ('res_id', '=', statement.id)]))

    def test_the_same_transactions_are_imported_once(self):
        self._import(QIF_FILE, 'statement.qif', journal_id=self.journal.id, date_format='%d/%m/%Y')
        with self.assertRaisesRegex(UserError, 'already imported'):
            self._import(QIF_FILE, 'statement.qif', journal_id=self.journal.id, date_format='%d/%m/%Y')

        # a file with one new transaction only brings that one in
        extended = QIF_FILE + 'D20/02/2026\nT-75.00\nPElectricity\n^\n'
        action = self._import(extended, 'statement2.qif', journal_id=self.journal.id, date_format='%d/%m/%Y')
        statement = self._statements_of(action)
        self.assertEqual(statement.line_ids.mapped('payment_ref'), ['Electricity'])

    def test_import_ofx_finds_the_journal_by_its_account_number(self):
        action = self._import(OFX_FILE, 'statement.ofx')
        statement = self._statements_of(action)
        self.assertEqual(statement.journal_id, self.journal)
        self.assertEqual(statement.balance_end_real, 3154.80)
        lines = statement.line_ids.sorted('date')
        self.assertEqual(lines.mapped('amount'), [-45.2, 1200.0])
        self.assertEqual(lines.mapped('payment_ref'), ['Coffee Shop', 'Salary'])
        self.assertEqual(lines[0].transaction_type, 'debit')
        self.assertEqual(str(lines[1].date), '2026-02-10')

    def test_a_file_of_another_journal_is_refused(self):
        other = self.env['account.journal'].create({
            'name': 'Second Bank', 'type': 'bank', 'code': 'BNK2',
        })
        with self.assertRaisesRegex(UserError, 'not to'):
            self._import(OFX_FILE, 'statement.ofx', journal_id=other.id)

    def test_a_statement_in_another_currency_is_refused(self):
        foreign = self.setup_other_currency('EUR')
        self.journal.currency_id = foreign
        with self.assertRaisesRegex(UserError, 'USD'):
            self._import(OFX_FILE, 'statement.ofx')

    def test_a_journal_is_needed(self):
        self.journal.bank_account_id = False
        with self.assertRaisesRegex(UserError, 'No journal'):
            self._import(QIF_FILE, 'statement.qif', date_format='%d/%m/%Y')

    def test_an_unknown_format_is_refused(self):
        with self.assertRaisesRegex(UserError, 'not supported'):
            self._import('nothing a bank would ever send', 'notes.txt', journal_id=self.journal.id)

    def _sample(self, file_name):
        with file_open('om_account_bank_statement_import/sample_files/%s' % file_name, 'rb') as file:
            return file.read()

    def test_the_layout_of_16_imports_without_a_map(self):
        """ The files of the import of 16.0 before the maps (Date, Label, Reference, Partner, Amount, Currency)
        import into a journal without a map of its own, as they did. """
        partner = self.env['res.partner'].create({'name': 'odoo mates'})
        self.assertFalse(self.journal.statement_import_map_id)
        action = self._import(self._sample('Import_Sample.csv'), 'Import_Sample.csv', journal_id=self.journal.id)
        lines = self._statements_of(action).line_ids.sorted('amount')
        self.assertEqual(lines.mapped('amount'), [30.0, 40.0])
        self.assertEqual(lines.mapped('payment_ref'), ['Test 1', 'Test 2'])
        self.assertEqual(lines.mapped('ref'), ['Ref 1', 'Ref 2'])
        self.assertEqual(lines.partner_id, partner)
        self.assertEqual(set(lines.mapped('date')), {date(2020, 12, 1)})

    def test_the_excel_layout_of_16_imports_without_a_map(self):
        self.env['res.partner'].create({'name': 'odoo mates'})
        self.env.ref('base.KWD').active = True
        action = self._import(self._sample('Import_Sample.xlsx'), 'Import_Sample.xlsx', journal_id=self.journal.id)
        lines = self._statements_of(action).line_ids.sorted('payment_ref')
        self.assertEqual(lines.mapped('payment_ref'), ['Test 1', 'Test 2'])
        self.assertEqual(lines.mapped('ref'), ['Ref 1', 'Ref 2'])
        self.assertTrue(lines.partner_id)

    def _import_csv_with_partners(self, rows):
        """ Import a CSV file of transactions given as (other party, its bank account, amount) """
        file_map = self.env['account.statement.import.map'].create({
            'name': 'Bank with the other party', 'date_format': '%d/%m/%Y',
            'column_date': 'Date', 'column_label': 'Label', 'column_amount': 'Amount',
            'column_partner': 'Counter Party', 'column_account_number': 'Account',
        })
        content = 'Date,Label,Amount,Counter Party,Account\n' + ''.join(
            f'01/03/2026,Transaction {index},{amount},{name},{account}\n'
            for index, (name, account, amount) in enumerate(rows, start=1))
        action = self._import(content, 'statement.csv', journal_id=self.journal.id, map_id=file_map.id)
        return self._statements_of(action).line_ids.sorted('payment_ref')

    def test_the_partner_is_found_from_the_name_of_the_other_party(self):
        """ Only a company is matched by name """
        Partner = self.env['res.partner']
        bluebell = Partner.create({'name': 'Bluebell Telecom Ltd', 'is_company': True})
        harbour = Partner.create({'name': 'Harbour  Print', 'is_company': True})
        Partner.create({'name': 'Harbour Print Services', 'is_company': True})
        acme = Partner.create({'name': 'Acme Corporation', 'is_company': True})
        Partner.create({'name': 'Jane Whitfield', 'parent_id': acme.id})
        Partner.create({'name': 'Northwind Traders', 'is_company': True})
        Partner.create({'name': 'NORTHWIND TRADERS', 'is_company': True})
        Partner.create({'name': 'Ravenmoor Council', 'is_company': True})
        Partner.create({'name': 'Old Supplier Ltd', 'is_company': True, 'active': False})
        Partner.create({'name': 'Sister Company Ltd', 'is_company': True,
                        'company_id': self.setup_company_data('Sister Company')['company'].id})

        lines = self._import_csv_with_partners([
            ('BLUEBELL TELECOM LTD', '', -10),        # 1. the exact name, whatever the case
            ('harbour print', '', -25),               # 2. and whatever the spaces; not the longer name
            ('BLUEBELL TELECOM', '', -15),            # 3. part of a name only: not certain
            ('Jane Whitfield', '', 120),              # 4. a person is not matched by name
            ('Northwind Traders', '', -80),           # 5. two companies: none rather than the wrong one
            ('Ravenmoor Council Tax', '', -150),      # 6. more than the name: not certain
            ('City Parking Fines', '', -60),          # 7. no such partner
            ('Old Supplier Ltd', '', -50),            # 8. an archived partner is left out
            ('Sister Company Ltd', '', -5),           # 9. a partner of another company is left out
        ])
        # the partner of exactly the name written by the bank comes first, as the import of 16.0 found it
        jane = Partner.search([('name', '=', 'Jane Whitfield')])
        northwind = Partner.search([('name', '=', 'Northwind Traders')])
        self.assertEqual([line.partner_id for line in lines],
                         [bluebell, harbour, Partner, jane, northwind, Partner, Partner, Partner, Partner])
        # the name written by the bank is kept
        self.assertEqual(lines[2].partner_name, 'BLUEBELL TELECOM')

    def test_the_partner_is_found_from_the_bank_account_of_the_other_party(self):
        Partner = self.env['res.partner']
        supplier = Partner.create({'name': 'Paper Mill Ltd', 'is_company': True})
        PartnerBank = self.env['res.partner.bank']
        PartnerBank.create({'acc_number': 'GB29 NWBK 6016 1331 9268 19', 'partner_id': supplier.id})
        Partner.create({'name': 'Paper Mill Trading', 'is_company': True})
        contractor = Partner.create({'name': 'Kestrel Builders', 'is_company': True})
        person = Partner.create({'name': 'Tom Kestrel', 'parent_id': contractor.id})
        PartnerBank.create({'acc_number': 'GB94 BARC 1020 1530 0934 59', 'partner_id': person.id})
        for owner in Partner.create([{'name': 'Shared One', 'is_company': True}, {'name': 'Shared Two'}]):
            PartnerBank.create({'acc_number': 'DE89 3704 0044 0532 0130 00', 'partner_id': owner.id})

        lines = self._import_csv_with_partners([
            ('PM LTD', 'gb29 nwbk 6016 1331 9268 19', -200),            # 1. the owner of the account
            ('Paper Mill Ltd', 'GB29NWBK60161331926819', -100),         # 2. the account and the name agree
            ('Paper Mill Trading', 'GB29NWBK60161331926819', -300),     # 3. they disagree: none
            ('T KESTREL', 'GB94BARC10201530093459', -400),              # 4. a contact's account: their company
            ('Shared One', 'DE89370400440532013000', -50),              # 5. two owners: none, whatever the name
        ])
        # the partner of exactly the name written by the bank comes first, as the import of 16.0 found it
        trading = Partner.search([('name', '=', 'Paper Mill Trading')])
        shared_one = Partner.search([('name', '=', 'Shared One')])
        self.assertEqual([line.partner_id for line in lines], [supplier, supplier, trading, contractor, shared_one])
