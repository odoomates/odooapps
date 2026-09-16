import datetime
from odoo import api, fields, models, _
from odoo.tools import SQL
from markupsafe import Markup


class FollowupPrint(models.TransientModel):
    _name = 'followup.print'
    _description = 'Print Follow-up & Send Mail to Customers'

    def _get_followup(self):
        if self.env.context.get('active_model',
                                'ir.ui.menu') == 'followup.followup':
            return self.env.context.get('active_id', False)
        company_id = self.env.company.id
        followp_id = self.env['followup.followup'].search(
            [('company_id', '=', company_id)], limit=1)
        return followp_id or False

    date = fields.Date('Follow-up Sending Date', required=True,
                       help="This field allow you to select a forecast date "
                            "to plan your follow-ups",
                       default=fields.Date.context_today)
    followup_id = fields.Many2one('followup.followup', 'Follow-Up',
                                  required=True, readonly=True,
                                  default=_get_followup)
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
        partner_list_ids = [partner.partner_id.id for partner in self.env[
            'followup.stat.by.partner'].browse(partner_list)]
        ids = self.env['res.partner'].search(
            ['&', ('id', 'not in', partner_list_ids), '|',
             ('payment_responsible_id', '!=', False),
             ('payment_next_action_date', '!=', False)])

        partners_to_clear = []
        for part in ids:
            if not part.unreconciled_aml_ids:
                partners_to_clear.append(part.id)
                part.action_done()
        return len(partners_to_clear)

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
        data = self
        company_id = data.company_id.id
        context = self.env.context
        self.env['account.move.line'].flush_model([
            'account_id', 'company_id', 'date', 'date_maturity', 'debit',
            'followup_line_id', 'full_reconcile_id', 'partner_id',
        ])
        self.env.cr.execute(SQL(
            '''SELECT
                    l.partner_id,
                    l.followup_line_id,
                    l.date_maturity,
                    l.date, l.id
                FROM account_move_line AS l
                LEFT JOIN account_account AS a
                ON (l.account_id=a.id)
                WHERE (l.full_reconcile_id IS NULL)
                AND a.account_type = 'asset_receivable'
                AND (l.partner_id is NOT NULL)
                AND (l.debit > 0)
                AND (l.company_id = %s)
                ORDER BY l.date''', company_id))
        move_lines = self.env.cr.fetchall()
        old = None
        fups = {}
        fup_id = context.get('followup_id') or data.followup_id.id
        current_date = fields.Date.to_date(context.get('date') or data.date)
        levels = self.env['followup.line'].search([('followup_id', '=', fup_id)], order='delay')
        for level in levels:
            delay = datetime.timedelta(days=level.delay)
            fups[old] = (current_date - delay, level.id)
            old = level.id

        partner_list = []
        to_update = {}

        for partner_id, followup_line_id, date_maturity, date, id in \
                move_lines:
            if not partner_id:
                continue
            if followup_line_id not in fups:
                continue
            stat_line_id = self.env['followup.stat.by.partner']._get_stat_id(partner_id, company_id)
            if date_maturity:
                if date_maturity <= fups[followup_line_id][0]:
                    if stat_line_id not in partner_list:
                        partner_list.append(stat_line_id)
                    to_update[str(id)] = {'level': fups[followup_line_id][1],
                                          'partner_id': stat_line_id}
            elif date and date <= fups[followup_line_id][0]:
                if stat_line_id not in partner_list:
                    partner_list.append(stat_line_id)
                to_update[str(id)] = {'level': fups[followup_line_id][1],
                                      'partner_id': stat_line_id}
        return {'partner_ids': partner_list, 'to_update': to_update}
