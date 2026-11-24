from odoo import _, api, fields, models
from odoo.exceptions import UserError

# the groups that see the menus of the statements
MENU_GROUPS = ('account.group_account_readonly', 'account.group_account_manager')


class AccountFinancialReportMenu(models.TransientModel):
    _name = 'account.financial.report.menu'
    _description = "Add a Financial Report to a Menu"

    @api.model
    def _default_parent_id(self):
        return self.env.ref('account.account_reports_legal_statements_menu', raise_if_not_found=False)

    report_id = fields.Many2one('account.financial.report', string="Report", required=True, ondelete='cascade')
    name = fields.Char(string="Menu Name", required=True)
    parent_id = fields.Many2one('ir.ui.menu', string="Parent Menu", required=True, ondelete='cascade',
                                default=_default_parent_id, domain=[('action', '=', False)],
                                help="The menu the new menu is placed under.")
    sequence = fields.Integer(default=50, help="The position of the menu among the menus of its parent.")

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if 'name' in fields and not values.get('name') and values.get('report_id'):
            values['name'] = self.env['account.financial.report'].browse(values['report_id']).name
        return values

    def action_create_menu(self):
        self.ensure_one()
        report = self.report_id
        if report.parent_id:
            raise UserError(_("Only a report itself can have a menu, not one of its sections."))
        report._remove_menu()
        groups = [self.env.ref(xmlid, raise_if_not_found=False) for xmlid in MENU_GROUPS]
        group_ids = [group.id for group in groups if group]
        action = self.env['ir.actions.server'].sudo().create({
            'name': self.name,
            'model_id': self.env['ir.model']._get_id('account.financial.report'),
            'state': 'code',
            'code': "action = env['account.financial.report'].browse(%d).action_open_report()" % report.id,
            'group_ids': [(6, 0, group_ids)],
        })
        menu = self.env['ir.ui.menu'].sudo().create({
            'name': self.name,
            'parent_id': self.parent_id.id,
            'sequence': self.sequence,
            'action': 'ir.actions.server,%d' % action.id,
            'group_ids': [(6, 0, group_ids)],
        })
        report.sudo().write({'menu_id': menu.id, 'menu_action_id': action.id})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
