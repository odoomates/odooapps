from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

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
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data['default_journal_bank']
        cls.journal.bank_account_id = cls.env['res.partner.bank'].create({
            'account_number': '987654321',
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
