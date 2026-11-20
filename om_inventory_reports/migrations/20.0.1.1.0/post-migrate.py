import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """The saved views and the scheduled reports of the inventory reports, moved to the report
    engine: a view keeps its report, options, owner and sharing, a schedule its view and recipients."""
    if not table_exists(cr, 'om_inventory_report_view'):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""SELECT id, name, report_key, options, user_id, shared, is_default, company_id
                    FROM om_inventory_report_view ORDER BY id""")
    views = {}
    for view_id, name, key, options, user_id, shared, is_default, company_id in cr.fetchall():
        model = 'om.inventory.report.%s' % key
        if model not in env:
            _logger.warning("Saved view %r of the unknown inventory report %r not moved", name, key)
            continue
        views[view_id] = env['om.report.view'].create({
            'name': name, 'report_model': model, 'options': options or {}, 'user_id': user_id,
            'shared': shared, 'is_default': is_default, 'company_id': company_id,
        }).id
    moved = 0
    if table_exists(cr, 'om_inventory_report_schedule'):
        cr.execute("""SELECT id, name, active, view_id, file_format, expand_all, interval, next_date, user_id,
                             company_id, last_sent
                        FROM om_inventory_report_schedule ORDER BY id""")
        schedules = cr.fetchall()
        recipients = {}
        if table_exists(cr, 'om_inventory_report_schedule_res_partner_rel'):
            cr.execute("""SELECT om_inventory_report_schedule_id, res_partner_id
                            FROM om_inventory_report_schedule_res_partner_rel""")
            for schedule_id, partner_id in cr.fetchall():
                recipients.setdefault(schedule_id, []).append(partner_id)
        for (schedule_id, name, active, view_id, file_format, expand_all, interval, next_date, user_id,
             company_id, last_sent) in schedules:
            if view_id not in views or not recipients.get(schedule_id):
                continue
            env['om.report.schedule'].create({
                'name': name, 'active': active, 'view_id': views[view_id], 'file_format': file_format,
                'expand_all': expand_all, 'interval': interval, 'next_date': next_date, 'user_id': user_id,
                'company_id': company_id, 'last_sent': last_sent,
                'partner_ids': [(6, 0, recipients[schedule_id])],
            })
            moved += 1
    _logger.info("Inventory reports: %s saved views and %s scheduled reports moved to the report engine",
                 len(views), moved)
