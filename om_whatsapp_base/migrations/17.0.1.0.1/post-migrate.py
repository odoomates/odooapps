from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ Upgrade to 17.0.1.0.1: the scheduled action of the profile pictures ran
    once only, then turned itself off (no numbercall): it runs for good. """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref('om_whatsapp_base.ir_cron_om_whatsapp_pictures', raise_if_not_found=False)
    if cron:
        cron.write({'numbercall': -1, 'active': True})
