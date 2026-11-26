from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.sql import column_exists, create_column

RELEASE_STATES = [('yes', 'Yes'), ('no', 'No'), ('exception', 'Exception')]


class AccountMove(models.Model):
    _inherit = 'account.move'

    om_release_state = fields.Selection(
        RELEASE_STATES, string='Release to Pay', compute='_compute_om_release_state', store=True, index=True,
        tracking=True, copy=False,
        help="Yes: every line matches its purchase order and receipt within the tolerances, the bill can be paid.\n"
             "No: the bill waits, e.g. for goods not received yet, or for a manual release.\n"
             "Exception: more is billed than ordered, or a price is above the purchase order beyond the tolerance.")
    om_release_forced = fields.Selection(
        [('yes', 'Yes'), ('no', 'No')], string='Forced Release to Pay', copy=False, tracking=True, readonly=True,
        help="Set by a manager: replaces the computed Release to Pay until it is set back to automatic.")
    om_release_reason = fields.Char(string='Release Reason', copy=False, tracking=True, readonly=True)
    om_3way_enabled = fields.Boolean(related='company_id.om_3way_enabled', string='3-Way Matching Enabled')
    om_match_line_ids = fields.Many2many(
        'account.move.line', string='Match Lines', compute='_compute_om_match_line_ids')
    om_receipt_ids = fields.Many2many('stock.picking', string='Receipts', compute='_compute_om_receipt_ids')
    om_receipt_count = fields.Integer(string='Receipt Count', compute='_compute_om_receipt_ids')

    def _auto_init(self):
        # created empty: only the vendor bills are computed, by the post init hook
        if not column_exists(self.env.cr, 'account_move', 'om_release_state'):
            create_column(self.env.cr, 'account_move', 'om_release_state', 'varchar')
        return super()._auto_init()

    @api.depends(
        'move_type', 'state', 'company_id', 'om_release_forced',
        'invoice_line_ids.om_match_state', 'invoice_line_ids.display_type',
    )
    def _compute_om_release_state(self):
        for move in self:
            company = move.company_id
            if move.move_type != 'in_invoice' or move.state == 'cancel' or not company.om_3way_enabled:
                move.om_release_state = False
            elif move.om_release_forced:
                move.om_release_state = move.om_release_forced
            else:
                states = set(move.invoice_line_ids.filtered(
                    lambda line: line.display_type == 'product').mapped('om_match_state'))
                states.discard('none')
                states.discard(False)
                if not states:
                    move.om_release_state = 'yes' if company.om_3way_no_po_policy == 'release' else 'no'
                elif states & {'qty', 'price'}:
                    move.om_release_state = 'exception'
                elif 'waiting' in states:
                    move.om_release_state = 'no'
                else:
                    move.om_release_state = 'yes'

    @api.depends('invoice_line_ids.purchase_line_id', 'invoice_line_ids.display_type')
    def _compute_om_match_line_ids(self):
        for move in self:
            move.om_match_line_ids = move.invoice_line_ids.filtered(
                lambda line: line.display_type == 'product' and line.purchase_line_id)

    @api.depends('invoice_line_ids.purchase_line_id')
    def _compute_om_receipt_ids(self):
        for move in self:
            pickings = move.invoice_line_ids.purchase_line_id.move_ids.picking_id.filtered(
                lambda picking: picking.picking_type_code == 'incoming')
            move.om_receipt_ids = pickings
            move.om_receipt_count = len(pickings)

    # ------------------------------------------------------------------------------------------------------------
    # Payment control
    # ------------------------------------------------------------------------------------------------------------

    def _om_not_released(self, policies=('warn', 'block')):
        """ Vendor bills not released to pay whose company controls the payments with one of the given policies. """
        return self.filtered(
            lambda move: move.move_type == 'in_invoice'
            and move.om_release_state in ('no', 'exception')
            and move.company_id.om_3way_enabled
            and move.company_id.om_3way_payment_policy in policies)

    def _om_check_payment_allowed(self):
        blocked = self._om_not_released(policies=('block',))
        if blocked:
            raise UserError(self.env._(
                "These vendor bills are not released to pay: %(bills)s\n"
                "Receive the goods, solve the exceptions or ask a manager to release them.",
                bills=', '.join(blocked.mapped('display_name'))))

    def action_force_register_payment(self):
        self._om_check_payment_allowed()
        return super().action_force_register_payment()

    # ------------------------------------------------------------------------------------------------------------
    # Exceptions
    # ------------------------------------------------------------------------------------------------------------

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.filtered(lambda move: move.om_release_state == 'exception'
                        and move.company_id.om_3way_activity)._om_schedule_exception_activity()
        return posted

    def _om_schedule_exception_activity(self):
        summary = self.env._('Vendor bill exception')
        for move in self:
            if move.activity_ids.filtered(lambda activity: activity.summary == summary):
                continue
            orders = move.invoice_line_ids.purchase_line_id.order_id
            user = orders.user_id[:1] or move.invoice_user_id or self.env.user
            lines = move.invoice_line_ids.filtered(lambda line: line.om_match_state in ('qty', 'price'))
            move.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=summary,
                note=self.env._(
                    'The bill does not match its purchase order: %(lines)s',
                    lines=', '.join(
                        f"{line.product_id.display_name or line.name} "
                        f"({dict(line._fields['om_match_state']._description_selection(self.env))[line.om_match_state]})"
                        for line in lines)),
                user_id=user.id,
            )

    # ------------------------------------------------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------------------------------------------------

    def action_om_force_release(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(self.env._('Only an accounting administrator can force the Release to Pay.'))
        bills = self.filtered(lambda move: move.move_type == 'in_invoice')
        if not bills:
            raise UserError(self.env._('Select vendor bills.'))
        return {
            'name': self.env._('Release to Pay'),
            'type': 'ir.actions.act_window',
            'res_model': 'om.release.force.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_ids': bills.ids},
        }

    def action_om_view_receipts(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('stock.action_picking_tree_all')
        action['context'] = {'create': False}
        if len(self.om_receipt_ids) == 1:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = self.om_receipt_ids.id
        else:
            action['domain'] = [('id', 'in', self.om_receipt_ids.ids)]
        return action
