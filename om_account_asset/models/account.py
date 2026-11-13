# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    asset_depreciation_ids = fields.One2many('account.asset.depreciation.line', 'move_id',
                                             string='Assets Depreciation Lines')

    def button_cancel(self):
        for move in self:
            for line in move.asset_depreciation_ids:
                line.move_posted_check = False
        return super(AccountMove, self).button_cancel()

    def action_post(self):
        # after the entries are posted: post_lines_and_close_asset() only closes an asset
        # whose depreciation entries are all posted, and the ones of this move are still
        # draft until super() runs, so calling it first never closed anything
        result = super(AccountMove, self).action_post()
        for move in self:
            for depreciation_line in move.asset_depreciation_ids:
                depreciation_line.post_lines_and_close_asset()
        return result
