from odoo.addons.om_hr_payroll.hooks import _set_contract_types


def migrate(cr, version):
    # the contracts there before payroll had no Employee Category, and none could be chosen: the contract
    # types were never loaded
    _set_contract_types(cr)
