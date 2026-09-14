import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Upgrade from 19.0 (or 20.0.1.0.0).

    The 19.0 asset form hid the ending date of assets using the 'Ending Date' time
    method, so such assets could be saved without it. The board computation and the
    new constraint need that date: take it from the last depreciation of the board,
    which is where the depreciation stopped until now, or fall back to the
    'Number of Entries' method when the asset has no board.

    Existing boards are not recomputed: the depreciation of running assets goes on
    with the amounts already scheduled.
    """
    if not version:
        return

    cr.execute("""
        UPDATE account_asset_asset asset
           SET method_end = board.last_date
          FROM (
                SELECT asset_id, MAX(depreciation_date) AS last_date
                  FROM account_asset_depreciation_line
                 GROUP BY asset_id
          ) board
         WHERE asset.id = board.asset_id
           AND asset.method_time = 'end'
           AND asset.method_end IS NULL
           AND board.last_date IS NOT NULL
     RETURNING asset.id
    """)
    fixed_ids = [asset_id for asset_id, in cr.fetchall()]
    if fixed_ids:
        _logger.info("om_account_asset: set the missing ending date of assets %s from their board", fixed_ids)

    cr.execute("""
        UPDATE account_asset_asset
           SET method_time = 'number'
         WHERE method_time = 'end'
           AND method_end IS NULL
     RETURNING id
    """)
    switched_ids = [asset_id for asset_id, in cr.fetchall()]
    if switched_ids:
        _logger.warning(
            "om_account_asset: assets %s use the 'Ending Date' time method without an ending date nor a board, "
            "they now use the 'Number of Entries' method", switched_ids)

    cr.execute("""
        UPDATE account_asset_category
           SET method_time = 'number'
         WHERE method_time = 'end'
           AND method_end IS NULL
     RETURNING id
    """)
    category_ids = [category_id for category_id, in cr.fetchall()]
    if category_ids:
        _logger.warning(
            "om_account_asset: asset categories %s use the 'Ending Date' time method without an ending date, "
            "they now use the 'Number of Entries' method", category_ids)

    cr.execute("""
        SELECT COUNT(*)
          FROM res_company
         WHERE id IN (SELECT DISTINCT company_id FROM account_asset_asset)
    """)
    if cr.fetchone()[0]:
        _logger.info(
            "om_account_asset: set the gain and loss accounts for assets in the Accounting settings "
            "to sell or dispose of assets")
