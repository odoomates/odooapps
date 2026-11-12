from . import models


def pre_init_hook(env):
    """ This module takes over the credit limit block of Odoo Accounting Community: the records keep their ids, so
    that the setting of each company and the users of the group survive the upgrade. """
    env.cr.execute("""
        UPDATE ir_model_data
           SET module = 'om_credit_limit'
         WHERE module = 'om_account_accountant'
           AND name IN ('group_credit_limit_override',
                        'field_res_company__credit_limit_block',
                        'field_res_config_settings__credit_limit_block')
    """)
