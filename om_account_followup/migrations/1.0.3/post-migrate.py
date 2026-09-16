import logging

_logger = logging.getLogger(__name__)

OLD_PLACEHOLDER = '{{ user.company_id.name }}'
NEW_PLACEHOLDER = '{{ env.company.name }}'


def migrate(cr, version):
    """ Upgrade to 1.0.3: the follow-up email templates are not updated (noupdate), so their
    subject still names the default company of the sending user instead of the company the
    follow-up is sent for. Replace that placeholder in every language of the subject. """
    if not version:
        return
    cr.execute("""
        UPDATE mail_template template
           SET subject = (
                SELECT jsonb_object_agg(term.key, replace(term.value, %(old)s, %(new)s))
                  FROM jsonb_each_text(template.subject) term
               )
          FROM ir_model_data data
         WHERE data.model = 'mail.template'
           AND data.module = 'om_account_followup'
           AND data.res_id = template.id
           AND template.subject::text LIKE %(pattern)s
     RETURNING template.id
    """, {'old': OLD_PLACEHOLDER, 'new': NEW_PLACEHOLDER, 'pattern': f'%{OLD_PLACEHOLDER}%'})
    _logger.info("om_account_followup: company placeholder updated in the subject of mail templates %s",
                 [template_id for template_id, in cr.fetchall()])
