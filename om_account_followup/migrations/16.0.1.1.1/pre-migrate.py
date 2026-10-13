def migrate(cr, version):
    # The cron was left with the default number of calls of Odoo 16, 1: it ran once and switched itself
    # off. It runs without limit from now on, and the one that switched itself off is switched on again.
    # Before the data is loaded, which sets the number of calls and hides the ones that ran out.
    cr.execute("""
        UPDATE ir_cron cron
           SET numbercall = -1,
               active = cron.active OR cron.numbercall = 0
          FROM ir_model_data data
         WHERE data.model = 'ir.cron' AND data.res_id = cron.id
           AND data.module = %s AND data.name = %s
           AND cron.numbercall >= 0
    """, ('om_account_followup', 'ir_cron_send_followups'))
