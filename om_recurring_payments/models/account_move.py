from odoo import _, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_stop_auto_post(self):
        """ The draft entries are not posted automatically any more, and no next entry of their recurrence is
        created. The posted entries are left as they are. """
        drafts = self.filtered(lambda move: move.state == 'draft' and move.auto_post != 'no')
        for move in drafts:
            move.message_post(body=_('Auto-post stopped (was: %s).', dict(
                move._fields['auto_post']._description_selection(self.env))[move.auto_post]))
        drafts.write({'auto_post': 'no'})
        return True
