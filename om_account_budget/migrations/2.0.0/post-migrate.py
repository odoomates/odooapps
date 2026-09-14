import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Upgrade to 2.0.0, once the models are renamed and the new fields created.

    * budgetary positions whose accounts are all income accounts become revenue positions
    * planned amounts become positive: costs were entered as negative amounts, the lines
      with a negative amount become expense lines and the positive ones revenue lines
    * lines with a paid date expect their whole amount at that date
    """
    if not version:
        return

    cr.execute("""
        UPDATE account_budget_position position
           SET budget_type = 'revenue'
         WHERE EXISTS (SELECT 1 FROM account_budget_position_account_rel rel WHERE rel.position_id = position.id)
           AND NOT EXISTS (
                SELECT 1
                  FROM account_budget_position_account_rel rel
                  JOIN account_account account ON account.id = rel.account_id
                 WHERE rel.position_id = position.id
                   AND account.account_type NOT IN ('income', 'income_other')
           )
     RETURNING id
    """)
    revenue_positions = [position_id for position_id, in cr.fetchall()]

    cr.execute("""
        UPDATE account_budget_line line
           SET budget_type = CASE
                   WHEN line.planned_amount > 0 THEN 'revenue'
                   WHEN line.planned_amount < 0 THEN 'expense'
                   ELSE COALESCE(position.budget_type, 'expense')
               END,
               planned_amount = ABS(line.planned_amount),
               distribution = CASE WHEN line.planned_date IS NOT NULL THEN 'at_date' ELSE 'spread' END,
               warning_level = 'none'
          FROM account_budget_line line2
     LEFT JOIN account_budget_position position ON position.id = line2.position_id
         WHERE line2.id = line.id
    """)
    _logger.info("om_account_budget: %s budget lines converted to positive amounts, revenue positions: %s",
                 cr.rowcount, revenue_positions)

    cr.execute("""
        SELECT line.id
          FROM account_budget_line line
          JOIN account_budget_position position ON position.id = line.position_id
         WHERE line.budget_type != position.budget_type
    """)
    mismatched = [line_id for line_id, in cr.fetchall()]
    if mismatched:
        _logger.warning(
            "om_account_budget: the planned amount of budget lines %s has the opposite sign of their budgetary "
            "position, check whether they are expenses or revenues", mismatched)

    cr.execute("""
        SELECT line.id
          FROM account_budget_line line
         WHERE line.distribution = 'at_date'
           AND (line.planned_date < line.date_from OR line.planned_date > line.date_to)
    """)
    outside = [line_id for line_id, in cr.fetchall()]
    if outside:
        _logger.warning(
            "om_account_budget: budget lines %s expect their amount at a date outside of their period, "
            "change that date before editing them", outside)

    # views of the module are loaded again by now: the remaining ones are customizations
    cr.execute("""
        SELECT view.id
          FROM ir_ui_view view
         WHERE view.arch_db::text ~ %s
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data data
                 WHERE data.model = 'ir.ui.view' AND data.res_id = view.id AND data.module = 'om_account_budget'
           )
    """, [r'crossovered[._]budget|general_budget_id|theoritical_amount|account\.budget\.post'])
    custom_views = [view_id for view_id, in cr.fetchall()]
    if custom_views:
        _logger.warning(
            "om_account_budget: views %s still use the former budget model or field names (crossovered.budget, "
            "general_budget_id, theoritical_amount...): update them to the new names", custom_views)
