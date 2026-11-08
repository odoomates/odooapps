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

OFX_FOREIGN_FILE = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS><CURDEF>USD
<BANKACCTFROM><BANKID>123456<ACCTID>987654321<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST><DTSTART>20260301<DTEND>20260331
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260302<TRNAMT>545.00<FITID>FX-1<NAME>Euro Customer
<ORIGCURRENCY><CURRATE>1.09<CURSYM>EUR</ORIGCURRENCY></STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260303<TRNAMT>-100.00<FITID>FX-2<NAME>Paris Hotel
<CURRENCY><CURRATE>1.09<CURSYM>EUR</CURRENCY></STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260304<TRNAMT>-20.00<FITID>FX-3<NAME>Local Shop</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>416.00<DTASOF>20260331</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

CSV_FOREIGN_FILE = """Date,Label,Amount,Original Amount,Original Currency
01/02/2026,Transfer from Europe,545.00,500.00,EUR
02/02/2026,Hotel in Paris,-109.00,100.00,eur
03/02/2026,Local shop,-20.00,,
04/02/2026,Same currency,-30.00,-30.00,USD
"""

CAMT_FOREIGN_FILE = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>FX</MsgId><CreDtTm>2026-04-05T02:00:00</CreDtTm></GrpHdr>
    <Stmt>
      <Id>FX-STMT</Id>
      <Acct><Id><Othr><Id>987654321</Id></Othr></Id><Ccy>USD</Ccy></Acct>
      <Ntry>
        <Amt Ccy="USD">109.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-04-02</Dt></BookgDt>
        <AcctSvcrRef>CAMT-FX-1</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <AmtDtls><InstdAmt><Amt Ccy="EUR">100.00</Amt></InstdAmt></AmtDtls>
          <RltdPties><Cdtr><Nm>Paris Hotel</Nm></Cdtr></RltdPties>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
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

    def test_import_in_a_credit_card_journal(self):
        """ A credit card journal takes its statements as a bank journal does, chosen or found by its account. """
        card = self.env['account.journal'].create({
            'name': 'Company Card', 'type': 'credit', 'code': 'CARD',
            'bank_account_id': self.env['res.partner.bank'].create({
                'account_number': '555500001111', 'partner_id': self.env.company.partner_id.id}).id,
        })
        action = self._import(QIF_FILE, 'card.qif', journal_id=card.id, date_format='%d/%m/%Y')
        statement = self._statements_of(action)
        self.assertEqual(statement.journal_id, card)
        self.assertEqual(statement.line_ids.mapped('journal_id'), card)
        self.assertEqual(sorted(statement.line_ids.mapped('amount')), [-100.5, 2500.0])

        # the account number of the file finds the card journal
        action = self._import(OFX_FILE.replace('987654321', '555500001111'), 'card.ofx')
        self.assertEqual(self._statements_of(action).journal_id, card)

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

    # -------------------------------------------------------------------------
    # Foreign currency of the lines
    # -------------------------------------------------------------------------
    def _foreign_map(self):
        return self.env['account.statement.import.map'].create({
            'name': 'Foreign Map',
            'date_format': '%d/%m/%Y',
            'column_date': 'Date',
            'column_label': 'Label',
            'column_amount': 'Amount',
            'column_amount_currency': 'Original Amount',
            'column_foreign_currency': 'Original Currency',
        })

    def _foreign_values(self, lines):
        return [(line.amount, line.foreign_currency_id.name or False, line.amount_currency)
                for line in lines.sorted('date')]

    def test_import_csv_with_a_foreign_amount(self):
        """ A row in another currency keeps its foreign amount, with the sign of its amount; a row in the
        currency of the journal has none. """
        self.setup_other_currency('EUR')
        action = self._import(CSV_FOREIGN_FILE, 'foreign.csv', journal_id=self.journal.id,
                              map_id=self._foreign_map().id)
        lines = self._statements_of(action).line_ids
        self.assertEqual(self._foreign_values(lines), [
            (545.0, 'EUR', 500.0),
            (-109.0, 'EUR', -100.0),
            (-20.0, False, 0.0),
            (-30.0, False, 0.0),
        ])

    def test_an_unknown_foreign_currency_is_refused(self):
        content = CSV_FOREIGN_FILE.replace(',eur', ',XYZ')
        with self.assertRaisesRegex(UserError, 'XYZ, which is unknown'):
            self._import(content, 'foreign.csv', journal_id=self.journal.id, map_id=self._foreign_map().id)

    def test_an_inactive_foreign_currency_is_refused(self):
        self.env.ref('base.CHF').active = False
        content = CSV_FOREIGN_FILE.replace(',eur', ',CHF').replace(',EUR', ',CHF')
        with self.assertRaisesRegex(UserError, 'Activate'):
            self._import(content, 'foreign.csv', journal_id=self.journal.id, map_id=self._foreign_map().id)

    def test_import_camt_with_an_instructed_amount(self):
        self.setup_other_currency('EUR')
        action = self._import(CAMT_FOREIGN_FILE, 'foreign.xml')
        statement = self._statements_of(action)
        self.assertEqual(statement.journal_id, self.journal)
        self.assertEqual(self._foreign_values(statement.line_ids), [(-109.0, 'EUR', -100.0)])

    def test_import_ofx_with_a_currency(self):
        """ ORIGCURRENCY: the amount was converted, CURRENCY: the amount is the foreign one. """
        self.setup_other_currency('EUR')
        action = self._import(OFX_FOREIGN_FILE, 'foreign.ofx')
        self.assertEqual(self._foreign_values(self._statements_of(action).line_ids), [
            (545.0, 'EUR', 500.0),
            (-109.0, 'EUR', -100.0),
            (-20.0, False, 0.0),
        ])

    def test_a_journal_is_needed(self):
        self.journal.bank_account_id = False
        with self.assertRaisesRegex(UserError, 'No journal'):
            self._import(QIF_FILE, 'statement.qif', date_format='%d/%m/%Y')

    def test_an_unknown_format_is_refused(self):
        with self.assertRaisesRegex(UserError, 'not supported'):
            self._import('nothing a bank would ever send', 'notes.txt', journal_id=self.journal.id)
