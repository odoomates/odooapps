from odoo import api, fields, models, _
from markupsafe import Markup


class FollowupPrint(models.TransientModel):
    _name = 'followup.print'
    _description = 'Print Follow-up & Send Mail to Customers'

    def _get_followup(self):
        if self.env.context.get('active_model',
                                'ir.ui.menu') == 'followup.followup':
            return self.env.context.get('active_id', False)
        return self.env['followup.followup']._get_default_plan() or False

    date = fields.Date('Follow-up Sending Date', required=True,
                       help="This field allow you to select a forecast date "
                            "to plan your follow-ups",
                       default=fields.Date.context_today)
    followup_id = fields.Many2one('followup.followup', 'Plan', required=True, default=_get_followup,
                                  domain="[('company_id', 'in', allowed_company_ids)]")
    partner_ids = fields.Many2many('followup.stat.by.partner',
                                   'partner_stat_rel', 'osv_memory_id',
                                   'partner_id', 'Partners', required=True)
    company_id = fields.Many2one('res.company', readonly=True,
                                 related='followup_id.company_id')

    def process_partners(self, partner_ids, data):
        partner_obj = self.env['res.partner']
        partner_ids_to_print = []
        nbmanuals = 0
        manuals = {}
        nbmails = 0
        nbunknownmails = 0
        nbprints = 0
        for partner in self.env['followup.stat.by.partner'].browse(
                partner_ids):
            if partner.max_followup_id.manual_action:
                partner_obj.do_partner_manual_action([partner.partner_id.id])
                nbmanuals = nbmanuals + 1
                key = partner.partner_id.payment_responsible_id.name or _(
                    "Anybody")
                if key not in manuals.keys():
                    manuals[key] = 1
                else:
                    manuals[key] = manuals[key] + 1
            if partner.max_followup_id.send_email:
                nbunknownmails += partner.partner_id.do_partner_mail()
                nbmails += 1
            if partner.max_followup_id.send_letter and not self.env.context.get('followup_automatic'):
                partner_ids_to_print.append(partner.id)
                nbprints += 1
                message = _("Follow-up letter of %s will be sent",
                            Markup("<i>%s</i>") % partner.partner_id.latest_followup_level_id.name)
                partner.partner_id.message_post(body=message)
        paragraph = Markup("<p>%s</p>")
        if nbunknownmails == 0:
            resulttext = paragraph % _("%s email(s) sent", nbmails)
        else:
            resulttext = paragraph % _(
                "%(count)s email(s) should have been sent, but %(unknown)s had unknown email address(es)",
                count=nbmails, unknown=nbunknownmails)
        resulttext += paragraph % _("%s letter(s) in report", nbprints)
        resulttext += paragraph % _("%s manual action(s) assigned:", nbmanuals)
        if manuals:
            resulttext += Markup("<ul>%s</ul>") % Markup().join(
                Markup("<li>%s: %s</li>") % (responsible, count)
                for responsible, count in manuals.items())
        needprinting = nbprints > 0
        result = {}
        action = partner_obj.do_partner_print(partner_ids_to_print, data)
        result['needprinting'] = needprinting
        result['resulttext'] = resulttext
        result['action'] = action or {}
        return result

    def do_update_followup_level(self, to_update, partner_list, date):
        for id in to_update.keys():
            if to_update[id]['partner_id'] in partner_list:
                self.env['account.move.line'].browse([int(id)]).write(
                    {'followup_line_id': to_update[id]['level'],
                     'followup_date': date})

    def clear_manual_actions(self, partner_list):
        """ The follow-up activities of the customers who have paid everything are done """
        partner_list_ids = self.env['followup.stat.by.partner'].browse(partner_list).partner_id.ids
        activity_type = self.env.ref('om_account_followup.mail_activity_type_followup')
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('activity_type_id', '=', activity_type.id),
            ('res_id', 'not in', partner_list_ids),
        ])
        partners = self.env['res.partner'].browse(activities.mapped('res_id')).exists()
        paid = partners.filtered(lambda partner: partner.payment_amount_due <= 0)
        done = activities.filtered(lambda activity: activity.res_id in paid.ids)
        if done:
            done.action_feedback(feedback=_('Nothing is due any more.'))
        return len(paid)

    def do_process(self):
        self = self.with_company(self.company_id)
        context = dict(self.env.context or {})

        tmp = self._get_partners_followp()
        partner_list = tmp['partner_ids']
        to_update = tmp['to_update']
        date = self.date
        data = self.read()[0]
        data['followup_id'] = data['followup_id'][0]

        self.do_update_followup_level(to_update, partner_list, date)
        restot_context = context.copy()
        restot = self.with_context(restot_context).process_partners(
            partner_list, data)
        context.update(restot_context)
        nbactionscleared = self.clear_manual_actions(partner_list)
        if nbactionscleared > 0:
            restot['resulttext'] += Markup("<p>%s</p>") % _(
                "%s partners have no credits and as such the "
                "action is cleared", nbactionscleared)
        resource_id = self.env.ref(
            'om_account_followup.view_om_account_followup_sending_results')
        context.update({'description': restot['resulttext'],
                        'needprinting': restot['needprinting'],
                        'report_data': restot['action']})
        return {
            'name': _('Send Letters and Emails: Actions Summary'),
            'context': context,
            'view_mode': 'list,form',
            'res_model': 'followup.sending.results',
            'views': [(resource_id.id, 'form')],
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def _get_partners_followp(self):
        """ The customers of the plan whose reminders are due, and the level each open item reaches.

        The excluded customers and the ones who promised to pay later are left alone.
        """
        company = self.company_id
        date = fields.Date.to_date(self.env.context.get('date') or self.date)
        plan = self.env['followup.followup'].browse(self.env.context.get('followup_id')) or self.followup_id
        Partner = self.env['res.partner'].with_company(company)
        lines = self.env['account.move.line'].sudo().search(
            self.env['account.move.line']._followup_open_domain(company))
        partners = Partner.browse(lines.partner_id.ids).filtered(
            lambda partner: partner._followup_plan() == plan
            and not partner.followup_excluded
            and not (partner.followup_promise_date and partner.followup_promise_date >= date))
        state = partners._followup_state(date)
        stat = self.env['followup.stat.by.partner']
        partner_list = []
        to_update = {}
        for partner, values in state.items():
            if not values['lines_due']:
                continue
            stat_line_id = stat._get_stat_id(partner.id, company.id)
            partner_list.append(stat_line_id)
            for line, level in values['lines_due'].items():
                to_update[str(line.id)] = {'level': level.id, 'partner_id': stat_line_id}
        return {'partner_ids': partner_list, 'to_update': to_update}
