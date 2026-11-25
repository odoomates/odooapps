from datetime import timedelta

from odoo import api, models
from odoo.tools import html2plaintext
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# the changes of the posted entries printed, the most recent first
MAX_CHANGES = 500
GROUPS = [
    ('account.group_account_manager', _lt('Administrator')),
    ('account.group_account_user', _lt('Full Accounting Features')),
    ('account.group_account_invoice', _lt('Invoicing')),
    ('account.group_account_readonly', _lt('Read-only')),
]
LOCK_FIELDS = ['fiscalyear_lock_date', 'tax_lock_date', 'sale_lock_date', 'purchase_lock_date', 'hard_lock_date']


class ReportAuditPack(models.AbstractModel):
    _name = 'report.om_account_audit.report_audit_pack'
    _description = 'Audit Pack Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        packs = self.env['account.audit.pack'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.audit.pack',
            'docs': packs,
            'sections': {pack.id: self._sections(pack) for pack in packs},
        }

    @api.model
    def _sections(self, pack):
        company = pack.company_id
        Move = self.env['account.move'].sudo()
        period = [('company_id', 'child_of', company.id), ('date', '>=', pack.date_from), ('date', '<=', pack.date_to)]
        posted = period + [('state', '=', 'posted')]
        counts = {
            'posted': Move.search_count(posted),
            'secured': Move.search_count(posted + [('inalterable_hash', '!=', False)]),
            'not_secured': Move.search_count(posted + [('inalterable_hash', '=', False)]),
            'draft': Move.search_count(period + [('state', '=', 'draft')]),
            'cancelled': Move.search_count(period + [('state', '=', 'cancel')]),
        }
        return {
            'check': self.env['account.integrity.check'].sudo()._last_check(company),
            'counts': counts,
            'changes': self._changes(pack),
            'locks': [(company._fields[name].get_description(self.env)['string'], company[name])
                      for name in LOCK_FIELDS if name in company._fields],
            'closings': self.env['account.period.closing'].sudo().search([
                ('company_id', '=', company.id), ('date_from', '<=', pack.date_to),
                ('date_to', '>=', pack.date_from)], order='date_from'),
            'users': self._users(company),
        }

    @api.model
    def _changes(self, pack):
        """ The changes logged on the journal entries of the company during the period, as the Audit Trail lists
            them. """
        messages = self.env['mail.message'].sudo().search([
            ('model', '=', 'account.move'), ('message_type', 'in', ('notification', 'tracking')),
            ('date', '>=', pack.date_from), ('date', '<', pack.date_to + timedelta(days=1)),
        ], order='date desc, id desc')
        moves = self.env['account.move'].sudo().browse(set(messages.mapped('res_id'))).exists()
        allowed = set(moves.filtered(lambda m: m.company_id == pack.company_id
                                     or m.company_id.parent_id == pack.company_id).ids)
        rows = []
        for message in messages:
            if message.res_id not in allowed:
                continue
            rows.append({
                'date': message.date,
                'author': message.author_id.display_name or '',
                'record': message.record_name or '',
                'description': html2plaintext(message.body or '').strip() or (message.subtype_id.name or ''),
            })
            if len(rows) >= MAX_CHANGES:
                break
        return rows

    @api.model
    def _users(self, company):
        users = []
        seen = set()
        for xmlid, label in GROUPS:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if not group:
                continue
            for user in group.sudo().all_user_ids.filtered(
                    lambda u: u.active and not u.share and company in u.company_ids).sorted('name'):
                if user.id in seen:
                    continue
                seen.add(user.id)
                users.append({'name': user.name, 'login': user.login, 'access': str(label)})
        return users
