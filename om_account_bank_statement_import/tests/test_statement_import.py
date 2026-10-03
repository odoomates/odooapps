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
