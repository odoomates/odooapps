from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import SQL

from odoo.addons.base.models.res_users import INDEX_SIZE, KEY_CRYPT_CONTEXT

MCP_SCOPES = ('mcp', 'mcp_read')


class ResUsersApikeys(models.Model):
    _inherit = 'res.users.apikeys'

    @api.model
    def _mcp_check_key(self, key):
        """Return (key id, user id, scope, name) of a valid MCP key, else None."""
        if not key or len(key) < INDEX_SIZE:
            return None
        self.env.cr.execute(SQL('''
            SELECT k.id, k.user_id, k.scope, k.name, k.key
              FROM %(table)s k
              JOIN res_users u ON (u.id = k.user_id)
             WHERE u.active
               AND k.index = %(index)s
               AND k.scope IN %(scopes)s
               AND (k.expiration_date IS NULL OR k.expiration_date >= now() at time zone 'utc')
        ''', table=SQL.identifier(self._table), index=key[:INDEX_SIZE], scopes=MCP_SCOPES))
        for key_id, user_id, scope, name, hashed in self.env.cr.fetchall():
            if KEY_CRYPT_CONTEXT.verify(key, hashed):
                return key_id, user_id, scope, name
        return None


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = 'res.users.apikeys.description'

    scope = fields.Selection(selection_add=[('mcp', 'MCP'), ('mcp_read', 'MCP (read only)')],
                             ondelete={'mcp': 'set default', 'mcp_read': 'set default'})

    def check_access_make_key(self):
        res = super().check_access_make_key()
        if any(desc.scope in MCP_SCOPES for desc in self) and not self.env.user.has_group('om_ai_mcp.group_mcp_user'):
            raise AccessError(self.env._('Only MCP users can create MCP keys. Ask your administrator for the '
                                         'MCP Server / MCP User access.'))
        return res
