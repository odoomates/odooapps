from odoo import Command, fields, models
from odoo.exceptions import UserError


class OmQualityCheck(models.Model):
    _inherit = 'om.quality.check'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', index='btree_not_null',
                                    check_company=True, readonly=True)
    production_state = fields.Selection(related='production_id.state', string='Order Status')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order', index='btree_not_null', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Centre', index='btree_not_null', readonly=True)
    disposition = fields.Selection(selection_add=[('rework', 'Rework')], ondelete={'rework': 'set null'})

    def _om_quality_lots(self):
        lots = super()._om_quality_lots()
        if not lots and self.production_id and not self.lot_name and self.production_id.state == 'done':
            lots = self.production_id.lot_producing_ids
        return lots

    def _prepare_alert_values(self):
        values = super()._prepare_alert_values()
        values.update({
            'production_id': self.production_id.id,
            'workorder_id': self.workorder_id.id,
            'workcenter_id': self.workcenter_id.id,
        })
        return values

    def _prepare_retest_values(self):
        values = super()._prepare_retest_values()
        values.update({
            'production_id': self.production_id.id,
            'workorder_id': self.workorder_id.id,
            'workcenter_id': self.workcenter_id.id,
        })
        return values

    def action_om_quality_rework(self):
        """ The goods are reworked, then checked again: a new check holds the order now. """
        self.ensure_one()
        if self.state != 'failed' or self.disposition:
            raise UserError(self.env._("Only a failed check without decision goes to rework."))
        retest = self.copy(self._prepare_retest_values())
        self.disposition = 'rework'
        production = self.production_id
        if production:
            production.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self.env._("Rework after the failed check %s", self.name),
                note=self.env._("Rework %(product)s, then record the check %(check)s.",
                                product=self.product_id.display_name or production.product_id.display_name,
                                check=retest.name),
                user_id=production.user_id.id or self.env.uid)
            production.message_post(body=self.env._(
                "Rework asked by the failed check %(check)s; the check %(retest)s records the result.",
                check=self._get_html_link(), retest=retest._get_html_link()))
        self.message_post(body=self.env._("Sent to rework: %s records the new result.", retest._get_html_link()))
        return retest._action_open_dialog()

    def action_om_quality_mrp_scrap(self):
        self.ensure_one()
        if self.state != 'failed' or self.disposition:
            raise UserError(self.env._("Only a failed check without decision is scrapped."))
        production = self.production_id
        action = production.action_scrap()
        context = action['context']
        context['default_om_quality_check_id'] = self.id
        if production.state == 'done' and self.product_id == production.product_id:
            lots = self._om_quality_lots()
            context.update({
                'default_product_id': self.product_id.id,
                'default_quantity': len(lots) if self.product_id.tracking == 'serial' and lots else production.qty_produced,
                'default_location_id': production.location_dest_id.id,
            })
            if lots:
                context['default_lot_ids'] = [Command.set(lots.ids)]
        return action

    def _dialog_actions(self):
        actions = super()._dialog_actions()
        own = []
        if self.production_id and self.state == 'failed' and not self.disposition and not self.is_overridden:
            own.append(('action_om_quality_rework', self.env._('Rework'), 'warning'))
            if self.production_id.state not in ('draft', 'cancel'):
                own.append(('action_om_quality_mrp_scrap', self.env._('Scrap'), 'danger'))
        return own + actions

    def _dialog_values(self):
        values = super()._dialog_values()
        if self.workorder_id:
            values['extra'].append([self.env._('Step'), self.workorder_id.name])
        if self.workcenter_id:
            values['extra'].append([self.env._('Work Centre'), self.workcenter_id.name])
        return values
