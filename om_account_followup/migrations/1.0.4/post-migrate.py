import logging

_logger = logging.getLogger(__name__)

OLD_PLACEHOLDER = '{{ user.company_id.name }}'
NEW_PLACEHOLDER = '{{ env.company.name }}'

COMPANY_RULES = (
    'om_account_followup_comp_rule',
    'om_account_followup_stat_by_partner_comp_rule',
    'om_account_followup_stat_comp_rule',
)
COMPANY_DOMAIN = "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"
OLD_COMPANY_DOMAIN = "('company_id','child_of',[user.company_id.id])"


def migrate(cr, version):
    """ Upgrade to 1.0.4. The records below are not updated (noupdate):

    - the subject of the follow-up email templates named the default company of the sending
      user instead of the company the follow-up is sent for;
    - the multi-company rules showed the records of the child companies of the default company
      of the user instead of the companies selected in the switcher.

    Only the records still holding the old value are changed: a template or a rule the customer
    adapted keeps its own text.
    """
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

    cr.execute("""
        UPDATE ir_rule rule
           SET domain_force = %(domain)s
          FROM ir_model_data data
         WHERE data.model = 'ir.rule'
           AND data.module = 'om_account_followup'
           AND data.name IN %(rules)s
           AND data.res_id = rule.id
           AND regexp_replace(rule.domain_force, '\\s', '', 'g') LIKE %(old)s
     RETURNING rule.id
    """, {'domain': COMPANY_DOMAIN, 'rules': COMPANY_RULES,
          'old': '%' + OLD_COMPANY_DOMAIN.replace(' ', '') + '%'})
    _logger.info("om_account_followup: multi-company rules %s now follow the selected companies",
                 [rule_id for rule_id, in cr.fetchall()])
