import logging
from collections import defaultdict
from datetime import timedelta

from odoo import api, SUPERUSER_ID
from odoo.tools.sql import column_exists, table_exists

from odoo.addons.om_account_asset.models.account_asset import _month_fraction

_logger = logging.getLogger(__name__)

LEGACY_LINE_TABLE = 'account_asset_depreciation_line'
BATCH_SIZE = 500


def migrate(cr, version):
    """ Upgrade to 2.0.0: the journal entries become the depreciation board.

    Every line of the former board is turned into a journal entry of the asset:

    * a line with its own entry: the entry is linked to the asset with the amount of the line,
      a draft one is posted on its date
    * a line of a running asset without entry: a draft entry is created, posted on its date
      (entries dated before the upgrade are posted by the next run of the auto-post job)
    * a line posted in a grouped entry, which cannot belong to each asset it depreciates:
      its amount is added to the depreciation before import of the asset

    The lines of draft assets are dropped, their board is computed again when needed.
    """
    if not version or not table_exists(cr, LEGACY_LINE_TABLE):
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False, 'tracking_disable': True})

    # the cron generating the entries is noupdate data, so it is not removed with the module data
    cron = env.ref('om_account_asset.account_asset_cron', raise_if_not_found=False)
    if cron:
        cron.unlink()

    cr.execute(f"""
        SELECT move_id
          FROM {LEGACY_LINE_TABLE}
         WHERE move_id IS NOT NULL
         GROUP BY move_id
        HAVING COUNT(DISTINCT asset_id) > 1
    """)
    grouped_move_ids = {move_id for move_id, in cr.fetchall()}

    cr.execute(f"""
        SELECT line.asset_id, line.amount, line.depreciation_date, line.move_id, line.name, move.state AS move_state
          FROM {LEGACY_LINE_TABLE} line
          JOIN account_asset_asset asset ON asset.id = line.asset_id
     LEFT JOIN account_move move ON move.id = line.move_id
         WHERE asset.state NOT IN ('draft', 'cancelled')
           AND line.depreciation_date IS NOT NULL
      ORDER BY line.asset_id, line.depreciation_date, line.sequence, line.id
    """)
    lines_by_asset = defaultdict(list)
    for row in cr.dictfetchall():
        lines_by_asset[row['asset_id']].append(row)

    has_resume_date = column_exists(cr, 'account_asset_asset', 'resume_depreciation_date')
    resume_dates = {}
    if has_resume_date:
        cr.execute("SELECT id, resume_depreciation_date FROM account_asset_asset WHERE resume_depreciation_date IS NOT NULL AND state = 'open'")
        resume_dates = dict(cr.fetchall())

    moves_to_create = []
    imported_amounts = defaultdict(float)
    grouped_drafts = set()
    skipped_assets = []
    linked_count = 0
    for asset in env['account.asset.asset'].browse(sorted(lines_by_asset)):
        category = asset.category_id
        accounts = category.account_depreciation_id | category.account_depreciation_expense_id
        can_create = bool(
            asset.state == 'open' and category.journal_id.active
            and len(accounts) == len(accounts.filtered('active')) and accounts
        )
        try:
            period_start = asset._get_lifetime_start()
        except Exception:  # noqa: BLE001 incomplete asset, the period start only documents the entry
            period_start = asset.date - timedelta(days=1)

        last_posted_date = False
        for row in lines_by_asset[asset.id]:
            line_date = row['depreciation_date']
            entry_type = 'revaluation' if 're-evaluation' in (row['name'] or '') else 'depreciation'
            if row['move_id'] in grouped_move_ids and row['move_state'] == 'posted':
                imported_amounts[asset.id] += row['amount']
            elif row['move_id'] and row['move_id'] not in grouped_move_ids and row['move_state'] != 'cancel':
                cr.execute("""
                    UPDATE account_move
                       SET depreciation_asset_id = %s,
                           asset_entry_type = %s,
                           asset_depreciation_amount = %s,
                           asset_period_start = %s,
                           auto_post = CASE WHEN state = 'draft' AND %s THEN 'at_date' ELSE auto_post END
                     WHERE id = %s
                """, [asset.id, entry_type, row['amount'], period_start, asset.state == 'open', row['move_id']])
                linked_count += 1
            elif asset.state == 'open':
                if row['move_id'] in grouped_move_ids:
                    grouped_drafts.add(row['move_id'])
                if not can_create:
                    skipped_assets.append(asset.id)
                    break
                moves_to_create.append({
                    **asset._prepare_depreciation_move_vals(row['amount'], period_start, line_date, entry_type=entry_type),
                    'auto_post': 'at_date',
                })
            if row['move_state'] == 'posted' and (not resume_dates.get(asset.id) or line_date < resume_dates[asset.id]):
                last_posted_date = line_date
            period_start = line_date

        # 1.1.0 kept the date of the next depreciation after a pause, the time on hold is
        # now added to the life of the asset
        resume_date = resume_dates.get(asset.id)
        if resume_date and last_posted_date:
            shift = (resume_date - asset._get_period_end_after(last_posted_date)).days
            if shift > 0:
                restart_date = last_posted_date + timedelta(days=shift)
                cr.execute("""
                    UPDATE account_asset_asset
                       SET paused_months = %s, depreciation_restart_date = %s
                     WHERE id = %s
                """, [_month_fraction(last_posted_date, restart_date - timedelta(days=1)), restart_date, asset.id])

    for asset_id, amount in imported_amounts.items():
        cr.execute("""
            UPDATE account_asset_asset
               SET opening_depreciation = COALESCE(opening_depreciation, 0) + %s
             WHERE id = %s
        """, [amount, asset_id])
    if grouped_drafts:
        env['account.move'].browse(grouped_drafts).filtered(lambda m: m.state == 'draft').unlink()

    # entries of the 1.1.0 disposals and value increases
    cr.execute("""
        UPDATE account_move move
           SET depreciation_asset_id = asset.id, asset_entry_type = 'disposal'
          FROM account_asset_asset asset
         WHERE move.id = asset.disposal_move_id AND move.depreciation_asset_id IS NULL
    """)
    cr.execute("""
        UPDATE account_move move
           SET depreciation_asset_id = asset.id, asset_entry_type = 'value_increase'
          FROM account_asset_asset asset
         WHERE move.id = asset.increase_move_id AND move.depreciation_asset_id IS NULL
    """)
    env.invalidate_all()

    Move = env['account.move'].with_context(tracking_disable=True, om_asset_board_update=True)
    for start in range(0, len(moves_to_create), BATCH_SIZE):
        Move.create(moves_to_create[start:start + BATCH_SIZE])

    _logger.info(
        "om_account_asset: linked %s depreciation entries, created %s entries posted on their date, "
        "moved the grouped depreciation of %s assets to their depreciation before import",
        linked_count, len(moves_to_create), len(imported_amounts))
    if skipped_assets:
        _logger.warning(
            "om_account_asset: assets %s have an archived journal or account, their remaining "
            "depreciation entries were not created: recompute them from the asset once fixed",
            sorted(set(skipped_assets)))
