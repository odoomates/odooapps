""" The text of sample vendor bills, in the layouts of several countries. """
US = """
                                                        INVOICE
Acme Office Supplies Inc.
1200 Market Street, Suite 400                                  Invoice No:   INV-2026-0042
San Francisco, CA 94103                                        Invoice Date: March 12, 2026
billing@acmeoffice.com                                         Due Date:     April 11, 2026
Tax ID: 94-1234567                                             PO Number:    PO00017

Bill To:
My Company (San Francisco)

 #   Description                          Qty      Unit Price        Amount
 1   Copy paper A4 80 g, box of 5          10          24.50        245.00
 2   Ink cartridge black XL                 4          38.75        155.00
 3   Desk organizer, bamboo                 2          19.99         39.98
     with drawer

                                                    Subtotal         439.98
                                                    Sales Tax 8.5%    37.40
                                                    Total            477.38
                                                    Amount Due    USD 477.38
"""
EU = """
Bürobedarf Müller GmbH
Hauptstraße 5, 10115 Berlin
USt-IdNr.: DE 123 456 789
IBAN: DE89 3704 0044 0532 0130 00

RECHNUNG                                   Rechnungsnummer: RE-58213
                                           Rechnungsdatum: 05.02.2026
                                           Fällig am: 07.03.2026

Pos  Bezeichnung                    Menge    Einzelpreis      Betrag
1    Ordner breit, blau               20          2,15         43,00
2    Kopierpapier 500 Blatt          100          4,10        410,00
3    Druckerservice (Stunden)          3         85,00        255,00

                                     Nettobetrag              708,00 €
                                     MwSt. 19 %               134,52 €
                                     Gesamtbetrag             842,52 €
"""
IN = """
SHREE TRADERS
GSTIN: 27AAPFU0939F1ZV
Tax Invoice No. ST/25-26/0193            Date: 14/08/2025

Sl  Particulars                 HSN     Qty    Rate      Amount
1   Steel Almirah               9403      2    8,500.00  17,000.00
2   Office Chair                9401      5    2,400.00  12,000.00

                                    Taxable Value      29,000.00
                                    CGST 9%             2,610.00
                                    SGST 9%             2,610.00
                                    Grand Total        34,220.00
"""
AE = """
GULF STATIONERY LLC
TRN: 100234567800003
TAX INVOICE
Invoice # GS-7781
Date 03/09/2026
Description                         Amount
Monthly maintenance contract        1,200.00
VAT 5%                                 60.00
Total AED                           1,260.00
"""
SIMPLE = """
Joe's Plumbing
joe@joesplumbing.com
Invoice 1187
2026-01-20
Repair of the kitchen sink, parts and labour.
TOTAL: $ 350.00
"""
REPEAT = """
Bürobedarf Müller GmbH
Hauptstraße 5, 10115 Berlin
USt-IdNr.: DE 123 456 789

RECHNUNG                                   Rechnungsnummer: RE-58377
                                           Rechnungsdatum: 03.04.2026

Pos  Bezeichnung                    Menge    Einzelpreis      Betrag
1    Kopierpapier 500 Blatt           50          4,10        205,00

                                     Nettobetrag              205,00 €
                                     MwSt. 19 %                38,95 €
                                     Gesamtbetrag             243,95 €
"""
NO_IDENTIFIER = """
Lakeside Catering
Catering for the staff party

Reference          Payable
LC-2026-118        Dated  04/03/2026

Buffet for 40 people, drinks included          Sum to pay   1,800.00
"""
NO_IDENTIFIER_NEXT = """
Lakeside Catering
Catering for the board meeting

Reference          Payable
LC-2026-131        Dated  05/03/2026

Lunch for 12 people                            Sum to pay     540.00
"""
# the text of an invoice printed by Odoo, as pdftotext reads it
ODOO_LAYOUT = """
Harbour Trading LLC
12 Dock Road
Dubai

Invoice INV/2026/00001

Invoice INV/2026/00001
Invoice Date
09/14/2026
Due Date
09/14/2026
                                        Unit
       Description         Quantity             Taxes Amount
                                        Price
Laser printer toner, black 6.00       72.50     15%   $ 435.00
Archive boxes (pack of 10) 3.00       18.90     15%   $ 56.70
On-site printer
                           2.00       95.00     15%   $ 190.00
maintenance
Untaxed
                $ 681.70
Amount
Tax 15%         $ 102.26
Total           $ 783.96


Payment Communication: INV/2026/00001




Page 1 /
1
"""
