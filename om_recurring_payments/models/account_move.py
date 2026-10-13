from odoo import _, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_stop_auto_post(self):
        """ The draft entries are not posted automatically any more. The posted entries are left as they are. """
        drafts = self.filtered(lambda move: move.state == 'draft' and move.auto_post)
        for move in drafts:
            move.message_post(body=_('Auto-post stopped.'))
        drafts.write({'auto_post': False})
        return True
