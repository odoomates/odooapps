from markupsafe import Markup

from odoo import api, SUPERUSER_ID
from odoo.tools.misc import format_date, formatLang


def migrate(cr, version):
    """ Upgrade to 1.2.0: the degressive factor is a yearly rate. It was applied to every period, so a degressive
    asset depreciated by month or by quarter lost the factor every month or quarter.

    Nothing is recomputed: the accountant decides. A note on each asset concerned keeps its lines not posted yet
    and says how to compute them again; a note on each category concerned asks to check its factor. """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    assets = env['account.asset.asset'].with_context(active_test=False).search([
        ('method', '=', 'degressive'),
        ('method_period', '<', 12),
        ('state', 'in', ('draft', 'open')),
    ])
    for asset in assets:
        drafts = asset.depreciation_line_ids.filtered(lambda line: not line.move_check).sorted('depreciation_date')
        rows = Markup('').join(
            Markup('<li>%s: %s</li>') % (format_date(env, line.depreciation_date),
                                         formatLang(env, line.amount, currency_obj=asset.currency_id))
            for line in drafts
        )
        body = Markup('<p>%s</p><p>%s</p>') % (
            env._('The degressive factor is now a yearly rate: %(factor)s depreciates %(percent)s%% of the value left at '
                  'the start of each year, spread over its periods. Before this version it was applied to every period of '
                  '%(months)s month(s).', factor=asset.method_progress_factor,
                  percent=round(asset.method_progress_factor * 100, 2), months=asset.method_period),
            env._('Nothing was changed. To compute the entries not posted yet with the yearly rate, press Compute '
                  'Depreciation; the posted ones stay as they are. If the factor was entered for a period on purpose, '
                  'leave the asset as it is.'),
        )
        if rows:
            body += Markup('<p>%s</p><ul>%s</ul>') % (env._('The entries not posted yet, before any change:'), rows)
        asset.message_post(body=body, subtype_xmlid='mail.mt_note')
        user = asset.create_uid
        if user and user.active and not user.share:
            asset.activity_schedule(
                'mail.mail_activity_data_todo', user_id=user.id,
                summary=env._('Check the degressive depreciation'),
                note=env._('The degressive factor is now a yearly rate; see the note of the asset.'))

    categories = env['account.asset.category'].with_context(active_test=False).search([
        ('method', '=', 'degressive'),
        ('method_period', '<', 12),
    ])
    for category in categories:
        category.message_post(body=env._(
            'The degressive factor is now a yearly rate: %(factor)s depreciates %(percent)s%% of the value left at the '
            'start of each year. Before this version it was applied to every period. If you entered a rate per '
            'period on purpose, enter the yearly rate instead, so that the new assets of this category depreciate '
            'as you expect.', factor=category.method_progress_factor,
            percent=round(category.method_progress_factor * 100, 2)), subtype_xmlid='mail.mt_note')
