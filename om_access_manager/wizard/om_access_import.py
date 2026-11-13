# Import access profiles from a file exported on another database.
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class OmAccessImport(models.TransientModel):
    _name = 'om.access.import'
    _description = 'Import Access Profiles'

    file = fields.Binary(string='File', required=True)
    filename = fields.Char()
    replace = fields.Boolean(
        string='Replace Profiles of the Same Name',
        help="A profile of this database with the same name is overwritten. Unticked, the "
             "imported one is created beside it, as '<name> (imported)'.")
    with_users = fields.Boolean(
        string='Also Assign the Users',
        help="Give the profiles to the users of the file, matched by login.")

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Choose the file to import."))
        content = base64.b64decode(self.file).decode('utf-8', errors='replace')
        profiles = self.env['om.access.profile']._om_import(
            content, replace=self.replace, with_users=self.with_users)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Imported Profiles"),
            'res_model': 'om.access.profile',
            'view_mode': 'list,form',
            'domain': [('id', 'in', profiles.ids)],
        }
