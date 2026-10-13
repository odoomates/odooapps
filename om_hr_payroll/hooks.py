CONTRACT_TYPES = (
    ('hr_contract_type_emp', 'Employee'),
    ('hr_contract_type_wrkr', 'Worker'),
    ('hr_contract_type_sub', 'Subcontractor'),
)


def _set_contract_types(cr):
    """ The Employee Category of the contracts is required, and the contract types of the module were never
    loaded on 17.0. Before they are:

    - a contract type of the same name made by the users becomes the module's one, kept as it is (no update),
      instead of a second type of the same name;
    - the contracts without a category get the Employee type, made here if there is none, so that the
      column can be made required. """
    # the name of the contract types of hr is translatable (jsonb)
    cr.execute("SELECT data_type FROM information_schema.columns "
               "WHERE table_name = 'hr_contract_type' AND column_name = 'name'")
    translated = cr.fetchone()[0] == 'jsonb'
    name_sql = "name->>'en_US'" if translated else "name"
    for xmlid, name in CONTRACT_TYPES:
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = 'om_hr_payroll' AND name = %s", (xmlid,))
        if cr.fetchone():
            continue
        cr.execute(f"SELECT id FROM hr_contract_type WHERE lower({name_sql}) = lower(%s) ORDER BY id LIMIT 1", (name,))
        row = cr.fetchone()
        if row:
            cr.execute("INSERT INTO ir_model_data (module, name, model, res_id, noupdate) "
                       "VALUES ('om_hr_payroll', %s, 'hr.contract.type', %s, true)", (xmlid, row[0]))

    cr.execute("SELECT 1 FROM hr_contract LIMIT 1")
    if not cr.fetchone():
        return
    cr.execute("SELECT column_name FROM information_schema.columns "
               "WHERE table_name = 'hr_contract' AND column_name = 'type_id'")
    if cr.fetchone():
        cr.execute("SELECT 1 FROM hr_contract WHERE type_id IS NULL LIMIT 1")
        if not cr.fetchone():
            return
    cr.execute("SELECT res_id FROM ir_model_data WHERE module = 'om_hr_payroll' AND name = 'hr_contract_type_emp'")
    row = cr.fetchone()
    if row:
        type_id = row[0]
    else:
        cr.execute("INSERT INTO hr_contract_type (name, create_uid, write_uid, create_date, write_date) "
                   "VALUES (%s, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC') RETURNING id",
                   ('{"en_US": "Employee"}' if translated else 'Employee',))
        type_id = cr.fetchone()[0]
        cr.execute("INSERT INTO ir_model_data (module, name, model, res_id, noupdate) "
                   "VALUES ('om_hr_payroll', 'hr_contract_type_emp', 'hr.contract.type', %s, false)", (type_id,))
    cr.execute("ALTER TABLE hr_contract ADD COLUMN IF NOT EXISTS type_id integer")
    cr.execute("UPDATE hr_contract SET type_id = %s WHERE type_id IS NULL", (type_id,))


def pre_init_hook(env):
    _set_contract_types(env.cr)
