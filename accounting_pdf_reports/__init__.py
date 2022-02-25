# -*- coding: utf-8 -*-

from . import wizards
from . import reports


def _pre_init_clean_m2m_models(cr):
    cr.execute("""DROP TABLE account_journal_account_report_partner_ledger_rel""")