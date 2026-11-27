from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .om_ai_field import SYNC_MAX_RECORDS
from .om_ai_field_engine import FILLABLE_TYPES


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('om_ai_fields', 'Update Fields with AI')],
        ondelete={'om_ai_fields': 'cascade'},
    )
    om_ai_field_def_id = fields.Many2one('om.ai.field', string='AI Field', ondelete='cascade', index='btree_not_null')
    om_ai_prompt = fields.Text(
        string='AI Prompt',
        help='What the AI is asked, with record values as {{ field }} or {{ field.sub_field }}.')
    om_ai_instructions = fields.Text(string='AI Instructions', help='Extra rules for the AI.')
    om_ai_target_field_ids = fields.Many2many(
        'ir.model.fields', 'ir_act_server_om_ai_field_rel', 'action_id', 'field_id', string='Fields to Fill',
        domain="[('model_id', '=', model_id), ('ttype', 'in', %s), ('readonly', '=', False), "
               "('store', '=', True)]" % (list(FILLABLE_TYPES),))
    om_ai_purpose = fields.Selection([('fast', 'Fast'), ('chat', 'Chat')], string='AI Purpose', default='fast')
    om_ai_model_id = fields.Many2one('om.ai.model', string='AI Model', domain=[('cap_chat', '=', True)])
    om_ai_overwrite = fields.Boolean(string='Replace Existing Values',
                                     help='Fill the fields even when they have a value.')

    def _name_depends(self):
        return [*super()._name_depends(), 'om_ai_target_field_ids']

    def _generate_action_name(self):
        self.ensure_one()
        if self.state == 'om_ai_fields' and self.om_ai_target_field_ids:
            return self.env._('Update %s with AI', ', '.join(self.om_ai_target_field_ids.mapped('field_description')))
        return super()._generate_action_name()

    @api.constrains('state', 'om_ai_prompt', 'model_id')
    def _check_om_ai_prompt(self):
        engine = self.env['om.ai.field.engine']
        for action in self.filtered(lambda a: a.state == 'om_ai_fields' and not a.om_ai_field_def_id):
            if not action.om_ai_prompt:
                continue
            try:
                engine._check_template(action.model_name, action.om_ai_prompt)
            except UserError as error:
                raise ValidationError(error.args[0]) from None

    def _om_ai_settings(self):
        """Prompt and options of the action, from its AI field when it has one."""
        self.ensure_one()
        ai_field = self.sudo().om_ai_field_def_id
        if ai_field:
            return {
                'fields': ai_field.field_id,
                'prompt': ai_field.prompt,
                'instructions': ai_field.instructions,
                'purpose': ai_field.purpose,
                'ai_model': ai_field.ai_model_id,
                'overwrite': ai_field.overwrite,
            }
        action = self.sudo()
        return {
            'fields': action.om_ai_target_field_ids,
            'prompt': action.om_ai_prompt,
            'instructions': action.om_ai_instructions,
            'purpose': action.om_ai_purpose,
            'ai_model': action.om_ai_model_id,
            'overwrite': action.om_ai_overwrite,
        }

    def _om_ai_fill_now(self, records):
        """Fill the fields of ``records`` now, as the current user."""
        self.ensure_one()
        ai_field = self.sudo().om_ai_field_def_id
        if ai_field:
            return ai_field.with_env(self.env)._fill_records(records)
        settings = self._om_ai_settings()
        if not settings['prompt'] or not settings['fields']:
            raise UserError(self.env._('The action "%s" has no AI prompt or no field to fill.', self.name))
        return self.env['om.ai.field.engine']._fill(
            records, settings['fields'], settings['prompt'], instructions=settings['instructions'],
            purpose=settings['purpose'], ai_model=settings['ai_model'], overwrite=settings['overwrite'])

    def _run_action_om_ai_fields_multi(self, eval_context=None):
        context = self.env.context
        if self.env.context.get('om_ai_fields_running') or self._is_recompute():
            return False
        res_ids = context.get('active_ids') or ([context['active_id']] if context.get('active_id') else [])
        if not res_ids:
            return False
        records = self.env[self.model_name].browse(res_ids).exists()
        # in automation rules and for many records: in the background, never blocking the save
        if context.get('__action_done') is not None or len(records) > SYNC_MAX_RECORDS:
            jobs = self.env['om.ai.field.job']._enqueue(self, records)
            if context.get('__action_done') is not None:
                return False
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': self.env._('Fill with AI'),
                    'message': self.env._('%s record(s) will be filled in the background.', len(jobs)),
                    'type': 'info',
                },
            }
        result = self._om_ai_fill_now(records)
        return self.env['om.ai.field.engine']._notify_result(result, title=self.name)
