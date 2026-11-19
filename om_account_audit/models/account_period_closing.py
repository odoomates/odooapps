from odoo import models


class AccountPeriodClosing(models.Model):
    _inherit = 'account.period.closing'

    def _get_closing_checks(self):
        checks = super()._get_closing_checks()
        company = self.company_id
        checks.append({
            'code': 'om_audit_not_secured',
            'name': self.env._('Posted entries not secured'),
            'sequence': 60,
            'level': 'warning',
            'model': 'account.move',
            'domain': [('company_id', 'child_of', company.id), ('state', '=', 'posted'),
                       ('date', '<=', self.date_to), ('inalterable_hash', '=', False)],
        })
        last = self.env['account.integrity.check']._last_check(company)
        checks.append({
            'code': 'om_audit_integrity',
            'name': self.env._('Last data inalterability check found changed entries'),
            'sequence': 70,
            'level': 'blocking',
            'model': 'account.integrity.check',
            'domain': [('id', '=', last.id if last.state == 'corrupted' else 0)],
        })
        return checks

    def action_close(self):
        """ The entries of the periods closed are secured, when the company asks for it. """
        open_closings = self.filtered(lambda closing: closing.state == 'open')
        result = super().action_close()
        for closing in open_closings.filtered(
                lambda closing: closing.state == 'closed' and closing.company_id.om_audit_secure_on_close):
            closing._om_secure_entries()
        return result

    def _om_secure_entries(self):
        self.ensure_one()
        wizard = self.env['account.secure.entries.wizard'].create({
            'company_id': self.company_id.id, 'hash_date': self.date_to})
        moves = wizard.move_to_hash_ids
        wizard.action_secure_entries()
        body = self.env._('%s entries secured up to the end of the period.', len(moves))
        if wizard.unreconciled_bank_statement_line_ids:
            body += ' ' + self.env._('The journals with bank transactions not reconciled are not secured yet.')
        self.message_post(body=body)
