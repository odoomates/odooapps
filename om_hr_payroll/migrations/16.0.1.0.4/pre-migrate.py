from odoo.addons.om_hr_payroll.hooks import _set_contract_types


def migrate(cr, version):
    # the contract types of the module were never loaded: bind or create them, and give the contracts
    # without an Employee Category the Employee one
    _set_contract_types(cr)
