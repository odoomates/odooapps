from odoo import models


class Base(models.AbstractModel):
    """ A record waiting for the approval of one of its buttons is read-only, when its flow locks it: nobody changes
    or deletes it until the approved button has run, or until an approval manager unlocks it. """
    _inherit = 'base'

    def write(self, vals):
        if self and not self.env.su and self._name in self.env['approval.rule']._locked_models():
            self.env['approval.request']._check_lock(self, list(vals))
        return super().write(vals)

    def unlink(self):
        if self and not self.env.su and self._name in self.env['approval.rule']._locked_models():
            self.env['approval.request']._check_lock(self)
        return super().unlink()

    def _approval_lock_exempt_fields(self):
        """ :return: the fields a locked record still lets change: its chatter, activities and followers """
        return {name for name in self._fields if name.startswith(('message_', 'activity_', 'website_message_'))} \
            | {'access_token'}
