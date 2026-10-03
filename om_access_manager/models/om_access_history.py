# Logs a note on the profile when one of its lines is added, changed or removed;
# mail.thread tracking only covers the profile's own fields.
from markupsafe import Markup

from odoo import _, api, models


class OmAccessHistoryMixin(models.AbstractModel):
    _name = 'om.access.history.mixin'
    _description = 'History of the Lines of an Access Profile'

    def _om_history_kind(self):
        """ What a line is, for the note: "data rule", "field"... """
        return self._description

    def _om_history_label(self):
        return self.display_name or ''

    def _om_log(self, verb, changed=()):
        lines = self.filtered(lambda line: line.profile_id)
        if not lines:
            return
        detail = ''
        if changed:
            detail = ' (%s)' % ', '.join(
                self._fields[name].string for name in changed if name in self._fields)
        for profile, profile_lines in lines.grouped('profile_id').items():
            items = Markup('').join(
                Markup('<li>%s%s</li>') % (line._om_history_label(), detail) for line in profile_lines)
            profile.message_post(
                body=Markup('<p>%s</p><ul>%s</ul>') % (
                    _("%(verb)s: %(kind)s", verb=verb, kind=self._om_history_kind()), items),
                subtype_xmlid='mail.mt_note',
            )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._om_log(_("Added"))
        return lines

    def write(self, vals):
        result = super().write(vals)
        self._om_log(_("Changed"), changed=[name for name in vals if name != 'profile_id'])
        return result

    def unlink(self):
        self._om_log(_("Removed"))
        return super().unlink()
