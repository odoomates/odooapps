from datetime import date

from odoo.addons.om_account_bank_statement_import.parsers import camt
from odoo.tests import TransactionCase, tagged

CAMT053 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>MSG-001</MsgId><CreDtTm>2023-02-01T02:00:00</CreDtTm></GrpHdr>
    <Stmt>
      <Id>STMT-2023-001</Id>
      <ElctrncSeqNb>1</ElctrncSeqNb>
      <CreDtTm>2023-02-01T02:00:00</CreDtTm>
      <Acct><Id><IBAN>BE68539007547034</IBAN></Id><Ccy>EUR</Ccy></Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2023-01-01</Dt></Dt>
      </Bal>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1150.50</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2023-01-31</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="EUR">250.50</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts>
        <BookgDt><Dt>2023-01-15</Dt></BookgDt><ValDt><Dt>2023-01-16</Dt></ValDt>
        <AcctSvcrRef>REF001</AcctSvcrRef>
        <BkTxCd><Domn><Cd>PMNT</Cd></Domn></BkTxCd>
        <AddtlNtryInf>SEPA CREDIT TRANSFER</AddtlNtryInf>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>E2E-001</EndToEndId></Refs>
          <RltdPties>
            <Dbtr><Nm>ACME Corp</Nm></Dbtr>
            <DbtrAcct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></DbtrAcct>
          </RltdPties>
          <RmtInf><Ustrd>Invoice 2023/0001</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">100.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
        <BookgDt><DtTm>2023-01-20T00:00:00</DtTm></BookgDt>
        <NtryRef>REF002</NtryRef>
        <NtryDtls><TxDtls>
          <RltdPties>
            <Cdtr><Pty><Nm>Electricity Ltd</Nm></Pty></Cdtr>
            <CdtrAcct><Id><IBAN>FR7630006000011234567890189</IBAN></Id></CdtrAcct>
          </RltdPties>
          <RmtInf><Ustrd>Energy bill</Ustrd></RmtInf>
          <AddtlTxInf>Direct debit of the month</AddtlTxInf>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""

CAMT053_BATCH = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>MSG-002</MsgId><CreDtTm>2023-03-01T02:00:00</CreDtTm></GrpHdr>
    <Stmt>
      <Id>STMT-2023-002</Id>
      <Acct><Id><IBAN>BE68539007547034</IBAN></Id><Ccy>EUR</Ccy></Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">225.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2023-02-28</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="EUR">300.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2023-02-10</Dt></BookgDt>
        <AcctSvcrRef>BATCH01</AcctSvcrRef>
        <AddtlNtryInf>Collection of the day</AddtlNtryInf>
        <NtryDtls>
          <Btch><NbOfTxs>2</NbOfTxs></Btch>
          <TxDtls>
            <Refs><EndToEndId>E2E-A</EndToEndId></Refs>
            <Amt Ccy="EUR">100.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
            <RltdPties><Dbtr><Nm>First Customer</Nm></Dbtr></RltdPties>
            <RmtInf><Ustrd>Invoice A</Ustrd></RmtInf>
          </TxDtls>
          <TxDtls>
            <Refs><EndToEndId>E2E-B</EndToEndId></Refs>
            <Amt Ccy="EUR">200.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
            <RltdPties><Dbtr><Nm>Second Customer</Nm></Dbtr></RltdPties>
            <RmtInf><Ustrd>Invoice B</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">75.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2023-02-11</Dt></BookgDt>
        <AcctSvcrRef>SINGLE01</AcctSvcrRef>
        <NtryDtls>
          <TxDtls><RltdPties><Cdtr><Nm>Office Supplies</Nm></Cdtr></RltdPties></TxDtls>
          <TxDtls><RmtInf><Ustrd>Order 42</Ustrd></RmtInf></TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""

CAMT052 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.02">
  <BkToCstmrAcctRpt>
    <GrpHdr><MsgId>MSG-003</MsgId><CreDtTm>2023-03-05T09:00:00</CreDtTm></GrpHdr>
    <Rpt>
      <Id>RPT-001</Id>
      <Acct><Id><Othr><Id>0001234567</Id></Othr></Id></Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>PRCD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="CHF">500.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2023-03-04</Dt></Dt>
      </Bal>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="CHF">400.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2023-03-05</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="CHF">100.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2023-03-05</Dt></BookgDt>
        <NtryRef>RPTREF1</NtryRef>
      </Ntry>
    </Rpt>
  </BkToCstmrAcctRpt>
</Document>
"""

CAMT054 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.02">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr><MsgId>MSG-004</MsgId><CreDtTm>2023-04-02T06:00:00</CreDtTm></GrpHdr>
    <Ntfctn>
      <Id>NTF-001</Id>
      <Acct><Id><IBAN>BE68539007547034</IBAN></Id><Ccy>EUR</Ccy></Acct>
      <Ntry>
        <Amt Ccy="EUR">42.00</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <ValDt><Dt>2023-04-01</Dt></ValDt>
        <AcctSvcrRef>NTF-ENTRY-1</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <RltdPties><Dbtr><Nm>Web Shop</Nm></Dbtr></RltdPties>
          <RmtInf><Ustrd>Order 1234</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
    </Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>
"""


@tagged('post_install', '-at_install')
class TestCamtParser(TransactionCase):

    def test_camt053_statement(self):
        """The header of a camt.053 statement: identification, account, currency and balances."""
        statements = camt.parse(CAMT053.encode(), 'statement.xml', {})
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement['name'], 'STMT-2023-001')
        self.assertEqual(statement['date'], date(2023, 1, 31))
        self.assertEqual(statement['account_number'], 'BE68539007547034')
        self.assertEqual(statement['currency_code'], 'EUR')
        self.assertEqual(statement['balance_start'], 1000.0)
        self.assertEqual(statement['balance_end_real'], 1150.50)
        self.assertEqual(len(statement['transactions']), 2)

    def test_camt053_transactions(self):
        """The signs of the entries and the values read from their details."""
        credit, debit = camt.parse(CAMT053.encode(), 'statement.xml', {})[0]['transactions']
        self.assertEqual(credit['amount'], 250.50)
        self.assertEqual(credit['date'], date(2023, 1, 15))
        self.assertEqual(credit['unique_import_id'], 'REF001')
        self.assertEqual(credit['partner_name'], 'ACME Corp')
        self.assertEqual(credit['account_number'], 'NL91ABNA0417164300')
        self.assertEqual(credit['payment_ref'], 'Invoice 2023/0001')
        self.assertEqual(credit['narration'], 'SEPA CREDIT TRANSFER')
        self.assertEqual(debit['amount'], -100.0)
        self.assertEqual(debit['date'], date(2023, 1, 20))
        self.assertEqual(debit['unique_import_id'], 'REF002')
        self.assertEqual(debit['partner_name'], 'Electricity Ltd')
        self.assertEqual(debit['account_number'], 'FR7630006000011234567890189')
        self.assertEqual(debit['narration'], 'Direct debit of the month')

    def test_camt053_batch_entry(self):
        """An entry whose details carry their own amount gives one transaction per detail."""
        transactions = camt.parse(CAMT053_BATCH.encode(), 'batch.xml', {})[0]['transactions']
        self.assertEqual(len(transactions), 3)
        first, second, single = transactions
        self.assertEqual([first['amount'], second['amount']], [100.0, 200.0])
        self.assertEqual([first['partner_name'], second['partner_name']],
                         ['First Customer', 'Second Customer'])
        self.assertEqual([first['unique_import_id'], second['unique_import_id']], ['E2E-A', 'E2E-B'])
        # the details of the last entry have no amount, they stay a single transaction
        self.assertEqual(single['amount'], -75.0)
        self.assertEqual(single['unique_import_id'], 'SINGLE01')
        self.assertEqual(single['partner_name'], 'Office Supplies')

    def test_camt052_report(self):
        """A camt.052 report, with a proprietary account number and its opening balance as PRCD."""
        statements = camt.parse(CAMT052.encode(), 'report.xml', {})
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement['name'], 'RPT-001')
        self.assertEqual(statement['account_number'], '0001234567')
        self.assertEqual(statement['currency_code'], 'CHF')  # no Acct/Ccy, taken from the entry
        self.assertEqual(statement['balance_start'], 500.0)
        self.assertEqual(statement['balance_end_real'], 400.0)
        self.assertEqual(statement['date'], date(2023, 3, 5))
        self.assertEqual(statement['transactions'][0]['amount'], -100.0)

    def test_camt054_notification(self):
        """A camt.054 notification has no balance and its entries can have a value date only."""
        statements = camt.parse(CAMT054.encode(), 'notification.xml', {})
        self.assertEqual(len(statements), 1)
        statement = statements[0]
        self.assertEqual(statement['name'], 'NTF-001')
        self.assertIsNone(statement['balance_start'])
        self.assertIsNone(statement['balance_end_real'])
        self.assertEqual(statement['date'], date(2023, 4, 2))
        self.assertEqual(len(statement['transactions']), 1)
        transaction = statement['transactions'][0]
        self.assertEqual(transaction['date'], date(2023, 4, 1))
        self.assertEqual(transaction['amount'], 42.0)
        self.assertEqual(transaction['partner_name'], 'Web Shop')

    def test_other_formats(self):
        """A file that is not a CAMT document is left to the next parser."""
        self.assertIsNone(camt.parse(b'OFXHEADER:100\nDATA:OFXSGML\n', 'file.ofx', {}))
        self.assertIsNone(camt.parse(b':20:1234\n:61:2301150115C250,50NTRF//X\n', 'file.sta', {}))
        self.assertIsNone(camt.parse(b'<?xml version="1.0"?><Document><Foo/></Document>', 'x.xml', {}))
