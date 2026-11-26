from odoo import api, fields, models
from odoo.fields import Domain

OPERATION_FIELDS = {
    'read': 'perm_read',
    'create': 'perm_create',
    'write': 'perm_write',
    'post': 'perm_write',
    'unlink': 'perm_unlink',
    'method': 'perm_method',
}


class OmMcpModelAccess(models.Model):
    """What MCP clients may do on a model. Models that are not listed are not
    available through MCP. The access rights and record rules of the user
    always apply on top of these permissions."""
    _name = 'om.mcp.model.access'
    _description = 'MCP Model Permission'
    _order = 'model, id'
    _rec_name = 'model_id'

    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade', index=True,
                               domain=[('transient', '=', False)])
    model = fields.Char(related='model_id.model', string='Technical Name', store=True)
    active = fields.Boolean(default=True)
    perm_read = fields.Boolean(string='Read', default=True)
    perm_create = fields.Boolean(string='Create')
    perm_write = fields.Boolean(string='Write', help='Update records, post in the chatter and attach files.')
    perm_unlink = fields.Boolean(string='Delete')
    perm_method = fields.Boolean(string='Server Actions', help='Run the server actions given to the AI as tools.')
    note = fields.Char()

    _model_unique = models.Constraint('UNIQUE(model_id)', 'A model may be listed only once.')

    @api.model
    def _get_permissions(self):
        """{model name: set of allowed operations} of the active permissions."""
        result = {}
        for access in self.sudo().search([]):
            ops = {op for op, fname in OPERATION_FIELDS.items() if access[fname]}
            if ops - {'read'}:
                ops.add('read')
            result[access.model] = ops
        return result

    @api.model
    def _allows(self, model_name, operation):
        access = self.sudo().search(Domain('model', '=', model_name), limit=1)
        fname = OPERATION_FIELDS.get(operation)
        if not access or not fname:
            return False
        return bool(access[fname] or (operation == 'read' and any(
            access[name] for name in OPERATION_FIELDS.values())))
