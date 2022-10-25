# -*- coding: utf-8 -*-

from odoo import models, fields, _


class Employee(models.Model):
    _inherit = "hr.employee"

    asset_count = fields.Integer(compute='_get_asset_count', string='# Assets')

    def _get_asset_count(self):
        for each in self:
            asset_ids = self.env['account.asset.asset'].sudo().search([('employee_id', '=', each.id)])
            if asset_ids:
                each.asset_count = len(asset_ids)
            else:
                each.asset_count = 0

    def action_asset_view(self):
        self.ensure_one()
        domain = [
            ('employee_id', '=', self.id)]
        return {
            'name': _('Assets'),
            'domain': domain,
            'res_model': 'account.asset.asset',
            'type': 'ir.actions.act_window',
            'view_id': self.env.ref('om_account_asset.view_account_asset_asset_purchase_tree').id,
            'view_mode': 'tree',
            'help': _('''<p class="oe_view_nocontent_create">
                           No assets allocated to the employee !
                        </p>'''),
            'context': {'create': 0, 'edit': 0, 'delete': 0, 'duplicate': 0},
        }
