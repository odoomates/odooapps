# Hide Activities, everywhere or for some data: the Activity button and the
# activities leave the chatter (the client reads has_activities), the activity
# view leaves the actions, the data leaves the systray, and what a client
# schedules, edits or marks done there is refused. Odoo's own code still
# schedules them: a confirmed document still plans its next step.
from odoo import _, api, models

# the methods of mail.activity a client calls to schedule, edit or close one
ACTIVITY_CLIENT_METHODS = (
    'create', 'write', 'unlink', 'web_save', 'action_done', 'action_feedback',
    'action_done_schedule_next', 'action_feedback_schedule_next', 'action_done_redirect_to_other',
    'action_reschedule_today', 'action_reschedule_tomorrow', 'action_reschedule_nextweek',
    'action_reschedule_customdate',
)


def hides_activities(env, model_name):
    rules = env['om.access.profile']._current_rules()
    return bool(model_name) and rules.enabled and rules.model_flag(model_name, 'hide_activities')


def refuse_activities(env, model_names, method):
    """ Refuse when the profiles of the current user hide the activities of one
    of ``model_names``. """
    for model_name in set(filter(None, model_names)):
        if hides_activities(env, model_name):
            raise env['om.access.profile']._om_refusal(
                _("Your access profile does not allow scheduling or changing activities on '%s'.",
                  env['ir.model']._get(model_name).name or model_name),
                model=model_name, method=method)


class IrModel(models.Model):
    _inherit = 'ir.model'

    def _om_drop_activities(self, model_definitions):
        for model_name, model_definition in model_definitions.items():
            if model_definition.get('has_activities') and hides_activities(self.env, model_name):
                model_definition['has_activities'] = False
        return model_definitions

    def _get_definitions(self, model_names):
        return self._om_drop_activities(super()._get_definitions(model_names))

    def _get_model_definitions(self, model_names_to_fetch):
        return self._om_drop_activities(super()._get_model_definitions(model_names_to_fetch))


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options)
        self.env['ir.model']._om_drop_activities(result.get('models') or {})
        return result


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def systray_get_activities(self):
        # the activities of the systray, as Odoo 17 lists them
        return [group for group in super().systray_get_activities()
                if not hides_activities(self.env, group.get('model'))]


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def _om_client_call(self):
        return any(self._om_rpc_entry(method) for method in ACTIVITY_CLIENT_METHODS)

    def _om_check_activities(self, extra_models=()):
        if self._om_client_call():
            refuse_activities(self.env, [*self.sudo().mapped('res_model'), *extra_models], 'mail.activity')

    @api.model_create_multi
    def create(self, vals_list):
        if self._om_client_call():
            IrModel = self.env['ir.model'].sudo()
            refuse_activities(self.env, [
                vals.get('res_model') or IrModel.browse(vals.get('res_model_id')).model
                or self.env.context.get('default_res_model')
                for vals in vals_list
            ], 'mail.activity')
        return super().create(vals_list)

    def write(self, vals):
        self._om_check_activities()
        return super().write(vals)

    def unlink(self):
        self._om_check_activities()
        return super().unlink()

    def _action_done(self, feedback=False, attachment_ids=None):
        self._om_check_activities()
        return super()._action_done(feedback=feedback, attachment_ids=attachment_ids)


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    def _om_check_schedule(self, method):
        if self._om_rpc_entry(method):
            refuse_activities(self.env, self.mapped('res_model'), method)

    def action_schedule_activities(self):
        self._om_check_schedule('action_schedule_activities')
        return super().action_schedule_activities()

    def action_schedule_activities_done(self):
        self._om_check_schedule('action_schedule_activities_done')
        return super().action_schedule_activities_done()

    def action_schedule_plan(self):
        self._om_check_schedule('action_schedule_plan')
        return super().action_schedule_plan()


class MailActivityMixin(models.AbstractModel):
    _inherit = 'mail.activity.mixin'

    def activity_schedule(self, *args, **kwargs):
        # passed on untouched: the parameters differ between versions of Odoo
        if self._om_rpc_entry('activity_schedule'):
            refuse_activities(self.env, [self._name], 'activity_schedule')
        return super().activity_schedule(*args, **kwargs)
