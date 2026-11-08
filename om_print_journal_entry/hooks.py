# These records were in accounting_pdf_reports. Where that module is installed, they are handed over to this
# module before its data is loaded: the same report and template are kept, with what the users changed on them, and
# the update of accounting_pdf_reports does not delete them.
MOVED_XMLIDS = ('report_journal_entries', 'action_report_journal_entries')


def pre_init_hook(env):
    cr = env.cr
    cr.execute("""
        UPDATE ir_model_data
           SET module = 'om_print_journal_entry'
         WHERE module = 'accounting_pdf_reports' AND name IN %s
    """, [MOVED_XMLIDS])
