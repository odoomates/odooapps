from odoo import Command, api, models

PAYMENT = 'account.payment'


class ApprovalRule(models.Model):
    _inherit = 'approval.rule'

    @api.model
    def _gallery_templates(self):
        return super()._gallery_templates() + [
            {'key': 'om_account_invoice', 'icon': 'request_quote', 'needs': ('om_account_move',),
             'name': self.env._('Customer invoices above an amount'),
             'description': self.env._('A customer invoice above an amount is posted once a manager approves '
                                       'it.')},
            {'key': 'om_account_refund', 'icon': 'undo', 'needs': ('om_account_move',),
             'name': self.env._('Approval of credit notes'),
             'description': self.env._('A customer or vendor credit note is posted once a manager approves it.')},
            {'key': 'om_account_entry', 'icon': 'edit_note', 'needs': ('om_account_move',),
             'name': self.env._('Approval of manual journal entries'),
             'description': self.env._('A journal entry of a miscellaneous journal is posted once a manager '
                                       'approves it.')},
        ]

    @api.model
    def _gallery_preset(self, model):
        if model == PAYMENT:
            preset = {
                'label': self.env._('Vendor Payments'), 'amount': 'amount', 'limit': 5000, 'high_limit': 20000,
                'domain': [('payment_type', '=', 'outbound')], 'confirm': 'action_post',
                'group': 'account.group_account_manager',
            }
            return {key: value for key, value in preset.items() if value}
        preset = super()._gallery_preset(model)
        if model == 'account.move':
            preset['om_account_move'] = True
        return preset

    @api.model
    def gallery_load(self, model=False, prefix=False):
        """ The vendor payments in the gallery too, next to the vendor bills. """
        result = super().gallery_load(model=model, prefix=prefix)
        if model == PAYMENT or PAYMENT not in self.env or (prefix and not PAYMENT.startswith(prefix)):
            return result
        extra = super().gallery_load(model=PAYMENT, prefix=prefix)
        templates = {template['key']: template for template in result['templates']}
        for template in extra['templates']:
            payment = [entry for entry in template['models'] if entry['model'] == PAYMENT]
            if not payment:
                continue
            if template['key'] in templates:
                templates[template['key']]['models'] += payment
            else:
                result['templates'].append(dict(template, models=payment))
        return result

    @api.model
    def _gallery_flow_values(self, key, model, preset):
        if not key.startswith('om_account_'):
            return super()._gallery_flow_values(key, model, preset)
        manager = {'name': self.env._('Accounting Manager'), 'approver_type': 'group',
                   'group_id': self._gallery_group(preset), 'remind_days': 1}
        values = {'button_id': self._gallery_button(model, 'action_post'), 'step_ids': [Command.create(manager)]}
        if key == 'om_account_invoice':
            limit = preset['limit']
            values.update(
                name=self.env._('Customer invoices above %s', f'{limit:,}'),
                domain=repr([('move_type', '=', 'out_invoice')]),
                amount_field='amount_total', amount_min=limit,
            )
        elif key == 'om_account_refund':
            values.update(
                name=self.env._('Credit notes'),
                domain=repr([('move_type', 'in', ['out_refund', 'in_refund'])]),
            )
        else:
            values.update(
                name=self.env._('Manual journal entries'),
                domain=repr([('move_type', '=', 'entry'), ('journal_id.type', '=', 'general')]),
            )
        return values
