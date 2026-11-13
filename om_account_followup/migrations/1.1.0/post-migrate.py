import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Upgrade to 1.1.0: the manual actions of the follow-ups are activities.

    The next actions written on the customers become activities of their responsible. The next actions
    themselves are left as they are, for the history.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    activity_type = env.ref('om_account_followup.mail_activity_type_followup', raise_if_not_found=False)
    if not activity_type:
        return
    partners = env['res.partner'].with_context(active_test=False).search([
        '|', ('payment_next_action', 'not in', [False, '']), ('payment_next_action_date', '!=', False),
    ])
    today = env.cr.now().date()
    for partner in partners:
        env['mail.activity'].create({
            'res_model_id': env['ir.model']._get_id('res.partner'),
            'res_id': partner.id,
            'activity_type_id': activity_type.id,
            'summary': 'Payment follow-up',
            'note': partner.payment_next_action or '',
            'date_deadline': partner.payment_next_action_date or today,
            'user_id': (partner.payment_responsible_id or env.ref('base.user_admin')).id,
        })
    _logger.info('om_account_followup: the next actions of %s customers became activities', len(partners))
