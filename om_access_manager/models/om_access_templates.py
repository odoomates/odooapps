# Ready-made profiles, kept as recipes in code rather than data so they never
# point to an app that is not installed; missing optional parts are skipped.
#
# A recipe:
#   key, name, description
#   requires      modules that must be installed for the recipe to be offered
#   any_app       True: the administrator picks the app, and every part of
#                 'apps' with 'app': None applies to it
#   apps          [{'app': menu xmlid, 'level': ..., 'own_records': bool,
#                   'optional': bool}], run through the Restrict an App engine
#   hide_menus    menu xmlids
#   models        {model: {perm_read/perm_create/perm_write/perm_unlink: bool}},
#                 applied after the apps, for what an app level cannot know
#   fields        [(model, field, mode)], mode as om.access.profile.field
#   switches      {profile field: value}
from odoo.tools.translate import _lt


TEMPLATES = [
    {
        'key': 'salesperson',
        'name': _lt("Salesperson"),
        'description': _lt(
            "Sells and follows their own customers, opportunities and quotations. "
            "No configuration, no sales reporting, no costs or margins, no export."),
        'requires': ['sale'],
        'apps': [
            {'app': 'sale.sale_menu_root', 'level': 'user', 'own_records': True},
            {'app': 'crm.crm_menu_root', 'level': 'user', 'own_records': True, 'optional': True},
        ],
        'hide_menus': ['sale.menu_sale_report'],
        'switches': {'block_export': True, 'hide_costs': True},
    },
    {
        'key': 'sales_readonly',
        'name': _lt("Sales Read Only"),
        'description': _lt("Sees the sales documents without changing them, and cannot export them."),
        'requires': ['sale'],
        'apps': [{'app': 'sale.sale_menu_root', 'level': 'readonly'}],
        'switches': {'block_export': True},
    },
    {
        'key': 'accountant',
        'name': _lt("Accountant without Configuration"),
        'description': _lt(
            "Does the daily accounting: invoices, bills, payments, entries and reports. "
            "The accounting configuration is hidden and read only."),
        'requires': ['account'],
        'apps': [{'app': 'account.menu_finance', 'level': 'user'}],
        # the app dashboard opens the journals, which are configuration
        'models': {'account.journal': {'perm_create': False, 'perm_write': False, 'perm_unlink': False}},
    },
    {
        'key': 'auditor',
        'name': _lt("Auditor"),
        'description': _lt(
            "Reads everything the Odoo groups of the user allow, changes nothing, "
            "and cannot export or import. The Settings app is hidden."),
        'requires': [],
        'switches': {
            'global_readonly': True,
            'block_export': True,
            'block_import': True,
            'hide_settings_menu': True,
        },
    },
    {
        'key': 'warehouse',
        'name': _lt("Warehouse Operator"),
        'description': _lt(
            "Receives, moves and delivers goods. No inventory configuration, no costs and "
            "no stock valuation."),
        'requires': ['stock'],
        'apps': [{'app': 'stock.menu_stock_root', 'level': 'user'}],
        'switches': {'hide_costs': True},
    },
    {
        'key': 'purchase',
        'name': _lt("Purchase User"),
        'description': _lt(
            "Creates and follows requests for quotation and purchase orders. "
            "The purchase configuration is hidden."),
        'requires': ['purchase'],
        'apps': [{'app': 'purchase.menu_purchase_root', 'level': 'user'}],
    },
    {
        'key': 'cashier',
        'name': _lt("Cashier"),
        'description': _lt(
            "Sells at the point of sale. The point of sale configuration, its reporting, the "
            "costs and the margins are hidden."),
        'requires': ['point_of_sale'],
        'apps': [{'app': 'point_of_sale.menu_point_root', 'level': 'user'}],
        'hide_menus': ['point_of_sale.menu_point_rep'],
        # the app dashboard opens the point of sale settings themselves
        'models': {'pos.config': {'perm_create': False, 'perm_write': False, 'perm_unlink': False}},
        'switches': {'hide_costs': True},
    },
    {
        'key': 'hr_officer',
        'name': _lt("HR Officer without Salaries"),
        'description': _lt(
            "Manages the employees without seeing their wage. The Payroll app is hidden "
            "when it is installed."),
        'requires': ['hr'],
        'apps': [{'app': 'hr.menu_hr_root', 'level': 'user'}],
        'hide_menus': ['om_hr_payroll.menu_hr_payroll_root'],
        'fields': [('hr.version', 'wage', 'hide')],
    },
    {
        'key': 'app_user',
        'name': _lt("App User without Configuration"),
        'description': _lt(
            "For any app: its configuration is hidden and read only, and the data of the "
            "app cannot be deleted."),
        'requires': [],
        'any_app': True,
        'apps': [{'app': None, 'level': 'user'}],
    },
    {
        'key': 'app_readonly',
        'name': _lt("App Read Only"),
        'description': _lt("For any app: everything in it can be read, nothing can be changed."),
        'requires': [],
        'any_app': True,
        'apps': [{'app': None, 'level': 'readonly'}],
    },
]

TEMPLATES_BY_KEY = {template['key']: template for template in TEMPLATES}
