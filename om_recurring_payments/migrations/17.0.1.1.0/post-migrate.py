def migrate(cr, version):
    # the responsible warned of the failed payments: the user who created the recurring payment
    cr.execute("UPDATE recurring_payment SET user_id = create_uid WHERE user_id IS NULL")
