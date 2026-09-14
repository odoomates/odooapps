def migrate(cr, version):
    """ Drop the data of the former depreciation board, converted by the post-migration. """
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS account_asset_depreciation_line CASCADE")
    cr.execute("DROP TABLE IF EXISTS asset_depreciation_confirmation_wizard CASCADE")
    cr.execute("ALTER TABLE account_asset_category DROP COLUMN IF EXISTS group_entries")
    cr.execute("ALTER TABLE account_asset_asset DROP COLUMN IF EXISTS resume_depreciation_date")
