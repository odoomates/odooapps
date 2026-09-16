from odoo.tools.sql import column_exists, rename_column

# 1.1.0 column -> 2.0.0 column
RENAMED_COLUMNS = {
    'already_depreciated_amount_import': 'opening_depreciation',
    'net_gain_on_sale': 'disposal_result',
    'gross_increase_move_id': 'increase_move_id',
}


def migrate(cr, version):
    """ Keep the values of the asset fields renamed in 2.0.0. """
    if not version:
        return
    for old_name, new_name in RENAMED_COLUMNS.items():
        if (column_exists(cr, 'account_asset_asset', old_name)
                and not column_exists(cr, 'account_asset_asset', new_name)):
            rename_column(cr, 'account_asset_asset', old_name, new_name)
