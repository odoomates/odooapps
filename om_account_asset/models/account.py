# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from markupsafe import Markup

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError

from .account_asset import BOARD_ENTRY_TYPES


class AccountMove(models.Model):
    _inherit = 'account.move'

    depreciation_asset_id = fields.Many2one(
        'account.asset.asset', string='Asset', index='btree_not_null', ondelete='restrict',
        copy=False, readonly=True,
        help="Asset whose value this entry depreciates, re-evaluates, increases or disposes of.",
    )
    asset_entry_type = fields.Selection([
        ('depreciation', 'Depreciation'),
        ('revaluation', 'Re-evaluation'),
        ('value_increase', 'Value Increase'),
        ('disposal', 'Disposal'),
        ('partial_disposal', 'Partial Disposal'),
        ('sale', 'Sale')],
        string='Asset Entry Type', copy=False, readonly=True,
    )
    asset_currency_id = fields.Many2one(related='depreciation_asset_id.currency_id', string='Asset Currency')
    asset_depreciation_amount = fields.Monetary(
        string='Depreciation', currency_field='asset_currency_id', copy=False,
        help="Value of the asset depreciated by this entry, in the currency of the asset.",
    )
    asset_disposed_value = fields.Monetary(
        string='Disposed Gross Value', currency_field='asset_currency_id', copy=False, readonly=True,
        help="Partial disposal: gross value removed from the asset, in the currency of the asset.",
    )
    asset_disposed_salvage = fields.Monetary(
        string='Disposed Salvage Value', currency_field='asset_currency_id', copy=False, readonly=True,
    )
    asset_disposed_opening = fields.Monetary(
        string='Disposed Opening Depreciation', currency_field='asset_currency_id', copy=False, readonly=True,
    )
    asset_period_start = fields.Date(
        string='Depreciated From', copy=False, readonly=True,
        help="Last day already depreciated before the period of this entry.",
    )
    asset_cumulative_depreciation = fields.Monetary(
        string='Cumulative Depreciation', currency_field='asset_currency_id',
        compute='_compute_asset_board_values',
    )
    asset_depreciable_value = fields.Monetary(
        string='Depreciable Value', currency_field='asset_currency_id',
        compute='_compute_asset_board_values',
        help="Value left to depreciate once this entry is posted.",
    )
    asset_book_value = fields.Monetary(
        string='Book Value', currency_field='asset_currency_id',
        compute='_compute_asset_board_values',
        help="Depreciable value plus salvage value once this entry is posted.",
    )
    asset_entry_reversed = fields.Boolean(string='Reversed', compute='_compute_asset_entry_reversed')

    @api.depends(
        'state', 'date', 'asset_depreciation_amount',
        'depreciation_asset_id.value', 'depreciation_asset_id.salvage_value',
        'depreciation_asset_id.opening_depreciation',
        'depreciation_asset_id.depreciation_move_ids.state',
        'depreciation_asset_id.depreciation_move_ids.date',
        'depreciation_asset_id.depreciation_move_ids.asset_depreciation_amount',
        'depreciation_asset_id.depreciation_move_ids.asset_disposed_value',
    )
    def _compute_asset_board_values(self):
        values = {}
        for asset in self.depreciation_asset_id:
            board = asset._get_board_moves().sorted(
                lambda m: (m.date or date.min, m.id if isinstance(m.id, int) else 0))
            partial_disposals = board.filtered(lambda m: m.asset_entry_type == 'partial_disposal' and m.state != 'cancel')
            # the values of the asset before its partial disposals
            opening = asset.opening_depreciation + sum(partial_disposals.mapped('asset_disposed_opening'))
            salvage = asset.salvage_value + sum(partial_disposals.mapped('asset_disposed_salvage'))
            value = asset.value + sum(partial_disposals.mapped('asset_disposed_value'))
            cumulative = opening
            depreciable = value - salvage - opening
            for move in board:
                if move.state != 'cancel':
                    cumulative += move.asset_depreciation_amount
                    depreciable -= move.asset_depreciation_amount
                    if move.asset_entry_type == 'partial_disposal':
                        cumulative -= move.asset_disposed_opening
                        salvage -= move.asset_disposed_salvage
                        depreciable -= (move.asset_disposed_value - move.asset_disposed_salvage
                                        - move.asset_disposed_opening)
                values[move.id] = (cumulative, depreciable, depreciable + salvage)
        for move in self:
            cumulative, depreciable, book = values.get(move.id, (0.0, 0.0, 0.0))
            move.asset_cumulative_depreciation = cumulative
            move.asset_depreciable_value = depreciable
            move.asset_book_value = book

    @api.depends('reversal_move_ids.state')
    def _compute_asset_entry_reversed(self):
        for move in self:
            move.asset_entry_reversed = bool(move.reversal_move_ids.filtered(lambda m: m.state == 'posted'))

    def action_open_asset_entry(self):
        """ Open the entry from the depreciation board of its asset. """
        self.ensure_one()
        return {
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': self.id,
        }

    def _is_asset_board_entry(self):
        self.ensure_one()
        return bool(self.depreciation_asset_id) and self.asset_entry_type in BOARD_ENTRY_TYPES

    @api.ondelete(at_uninstall=False)
    def _unlink_except_asset_board(self):
        if self.env.context.get('om_asset_board_update'):
            return
        for move in self:
            if move._is_asset_board_entry() and move.depreciation_asset_id.state in ('open', 'paused'):
                raise UserError(_(
                    'The entry %(entry)s is part of the depreciation board of "%(asset)s": use the actions of '
                    'the asset (modify, pause, sell or dispose, cancel) to change its board.',
                    entry=move.display_name, asset=move.depreciation_asset_id.name,
                ))

    def button_draft(self):
        self._check_asset_partial_disposal_kept()
        return super().button_draft()

    def button_cancel(self):
        self._check_asset_partial_disposal_kept()
        return super().button_cancel()

    def _check_asset_partial_disposal_kept(self):
        if self.env.context.get('om_asset_board_update'):
            return
        for move in self:
            if move.asset_entry_type == 'partial_disposal' and move.depreciation_asset_id.state != 'cancelled':
                raise UserError(_(
                    'The entry %(entry)s records the partial disposal of "%(asset)s": cancel the asset to remove it.',
                    entry=move.display_name, asset=move.depreciation_asset_id.name,
                ))

    def write(self, vals):
        if 'asset_depreciation_amount' not in vals or self.env.context.get('om_asset_skip_amount_sync'):
            return super().write(vals)
        board_moves = self.filtered(lambda m: m._is_asset_board_entry())
        if board_moves.filtered(lambda m: m.state != 'draft'):
            raise UserError(_('Only the depreciation of draft entries can be changed.'))
        res = super().write(vals)
        for move in board_moves:
            move._sync_asset_depreciation_lines()
        if not self.env.context.get('om_asset_no_rebalance'):
            # the next entries absorb the difference so that the board still ends at 0
            for asset, moves in board_moves.grouped('depreciation_asset_id').items():
                asset._recompute_board(keep_until=max(moves.mapped('date')))
        return res

    def _sync_asset_depreciation_lines(self):
        """ Report `asset_depreciation_amount` on the journal items of the entry. """
        self.ensure_one()
        asset = self.depreciation_asset_id
        company = asset.company_id
        lines = self.line_ids.sorted('id')
        if len(lines) != 2:
            raise UserError(_('The entry %s does not have the two journal items of a depreciation.', self.display_name))
        amount = self.asset_depreciation_amount
        balance = asset.currency_id._convert(amount, company.currency_id, company, self.date)
        depreciation_line, expense_line = lines
        self.with_context(om_asset_skip_amount_sync=True).write({'line_ids': [
            Command.update(depreciation_line.id, {'balance': -balance, 'amount_currency': -amount}),
            Command.update(expense_line.id, {'balance': balance, 'amount_currency': amount}),
        ]})

    def _post(self, soft=True):
        for move in self:
            if move._is_asset_board_entry() and move.depreciation_asset_id.state == 'draft':
                raise UserError(_('Confirm the asset "%s" before posting its depreciation entries.',
                                  move.depreciation_asset_id.name))
        posted = super()._post(soft=soft)
        posted.filtered(lambda m: m._is_asset_board_entry()).depreciation_asset_id._close_if_depreciated()
        return posted

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if not default_values_list:
            default_values_list = [{} for _move in self]
        if self.env.context.get('om_asset_board_update'):
            return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

        self._check_asset_partial_disposal_kept()
        board_moves = self.filtered(lambda m: m._is_asset_board_entry() and m.state == 'posted')
        for move, default_values in zip(self, default_values_list):
            if move in board_moves:
                default_values.update({
                    'depreciation_asset_id': move.depreciation_asset_id.id,
                    'asset_entry_type': move.asset_entry_type,
                    'asset_depreciation_amount': -move.asset_depreciation_amount,
                    'asset_period_start': default_values.get('date') or move.date,
                })
        reverse_moves = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        for move in board_moves:
            move.depreciation_asset_id._reschedule_reversed_depreciation(move)
        return reverse_moves


class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    def _reschedule_reversed_depreciation(self, reversed_move):
        """ The depreciation of a reversed entry did not happen: add it to the next draft
        entry of the board, or to a new entry when there is none. """
        self.ensure_one()
        amount = reversed_move.asset_depreciation_amount
        if self.state == 'close' and not self.disposal_date:
            self.write({'state': 'open'})
        if self.state == 'open':
            next_move = self._get_board_moves().filtered(lambda m: m.state == 'draft').sorted(lambda m: (m.date, m.id))[:1]
            if next_move:
                next_move.with_context(om_asset_no_rebalance=True).asset_depreciation_amount += amount
            else:
                cursor = max(self._get_board_cursor(self._get_board_moves()), fields.Date.context_today(self))
                move = self.env['account.move'].create(
                    self._prepare_depreciation_move_vals(amount, cursor, self._get_period_end_after(cursor)))
                move._post(soft=True)
        self.message_post(body=_(
            'Depreciation entry %(entry)s reversed, its depreciation is added to the next entry.',
            entry=reversed_move._get_html_link(),
        ))
