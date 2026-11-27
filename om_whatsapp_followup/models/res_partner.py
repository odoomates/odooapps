from odoo import fields, models
from odoo.exceptions import AccessError
from odoo.tools.misc import format_date, formatLang

# the overdue invoices listed in one WhatsApp message, the others counted
MAX_INVOICES = 10


def send_template(records, template, account):
    """ Send ``template`` from ``records`` without a user at the screen. With
    no account to send from, the documents say so in their chatter. """
    account = account or template.account_id or records.env['om.social.account']._get_default_account('whatsapp')
    if not account:
        for record in records:
            record._message_log(body=records.env._(
                "The WhatsApp %(template)s was not sent: choose the WhatsApp account to send from in the settings.",
                template=template.name))
        return records.env['mail.message']
    return records._message_om_whatsapp_template(template.sudo(), account=account)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _om_whatsapp_followup_check(self):
        """ The amounts and payment links of a customer are for the
        accounting users, and for the follow-ups sent without them. """
        if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(self.env._("Only the invoicing users see the amounts due of a customer."))

    def om_whatsapp_followup_amount(self):
        """ The amount overdue of the customer, with its currency. """
        self.ensure_one()
        self._om_whatsapp_followup_check()
        partner = self.commercial_partner_id
        return formatLang(self.env, partner.payment_amount_overdue, currency_obj=self.env.company.currency_id)

    def om_whatsapp_followup_invoices(self):
        """ The overdue invoices of the customer on one line, each with what is
        left to pay, its due date and the link to pay it online. """
        self.ensure_one()
        self._om_whatsapp_followup_check()
        partner = self.commercial_partner_id
        items = [
            (item, currency['currency'])
            for currency in partner._followup_statement_lines(overdue_only=True)
            for item in currency['lines'] if not item['disputed'] and item['residual'] > 0
        ]
        parts = []
        for item, currency in items[:MAX_INVOICES]:
            text = self.env._("%(invoice)s (%(amount)s, due %(date)s)",
                              invoice=item['name'], amount=formatLang(self.env, item['residual'], currency_obj=currency),
                              date=format_date(self.env, item['date_maturity']))
            if item['portal_url']:
                text += ' ' + partner.get_base_url() + item['portal_url']
            parts.append(text)
        if len(items) > MAX_INVOICES:
            parts.append(self.env._("and %(count)s more", count=len(items) - MAX_INVOICES))
        return '; '.join(parts) or '-'

    # ------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------

    def _om_whatsapp_followup_send(self, level=None):
        """ Send the WhatsApp reminder of ``level`` to each customer, logged in
        its chatter. A customer without a valid number gets a note instead; a
        sending problem never stops the follow-up.

        :return: the customers a WhatsApp was sent (or queued) to
        """
        sent = self.browse()
        default = self.env['followup.line']._om_whatsapp_default_template()
        for partner in self:
            template = (level and level.whatsapp_template_id) or default
            if not template:
                continue
            if not partner._phone_get_recipients_info()[partner.id]['sanitized']:
                partner.message_post(body=self.env._("The reminder could not be sent by WhatsApp: the customer has no "
                                                     "valid mobile number."))
                continue
            plan = (level and level.followup_id) or partner._followup_plan()
            if send_template(partner, template, plan.om_whatsapp_account_id):
                sent |= partner
        return sent

    def _followup_process(self, date=None, send_email=None, print_letter=None, template=None, subject=None,
                          body=None, recipients=None, attach_invoices=False, levels=None):
        """ The WhatsApp of the level goes with its other actions; the
        context key ``followup_send_whatsapp`` (True or False) overrides the
        level, as the email and letter options do. """
        forced = self.env.context.get('followup_send_whatsapp')
        state = self._followup_state(date or fields.Date.context_today(self))
        targets = {}
        for partner in self:
            level = (levels or {}).get(partner) or state[partner]['level_due'] or partner.latest_followup_level_id
            if (forced if forced is not None else bool(level.send_whatsapp)):
                targets[partner] = level
        result = super()._followup_process(
            date=date, send_email=send_email, print_letter=print_letter, template=template, subject=subject,
            body=body, recipients=recipients, attach_invoices=attach_invoices, levels=levels)
        whatsapp = self.browse()
        for partner, level in targets.items():
            whatsapp |= partner._om_whatsapp_followup_send(level)
        result['whatsapp'] = whatsapp
        return result
