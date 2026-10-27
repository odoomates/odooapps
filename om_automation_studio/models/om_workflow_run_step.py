from odoo import api, fields, models

# the name of each type of step, when it has no label of its own
NODE_TYPES = [
    ('start', 'Start'),
    ('condition', 'Condition'),
    ('wait', 'Wait'),
    ('wait_until', 'Wait Until'),
    ('approval', 'Approval'),
    ('update', 'Update Record'),
    ('create', 'Create Record'),
    ('email', 'Send Email'),
    ('activity', 'Schedule Activity'),
    ('note', 'Post Message'),
    ('end', 'End'),
]


class OmWorkflowRunStep(models.Model):
    """ A step a run went through: when, and by which exit it left. """
    _name = 'om.workflow.run.step'
    _description = 'Workflow Run Step'
    _order = 'id'

    run_id = fields.Many2one('om.workflow.run', required=True, ondelete='cascade', index=True)
    node_key = fields.Char(required=True)
    node_label = fields.Char('Step')
    node_type = fields.Selection(NODE_TYPES, 'Type', required=True)
    port = fields.Char('Exit')
    state = fields.Selection([
        ('running', 'Running'),
        ('waiting', 'Waiting'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True)
    date_start = fields.Datetime('Started', default=fields.Datetime.now, required=True)
    date_end = fields.Datetime('Ended')
    message = fields.Char()

    @api.model
    def _label(self, node):
        return node.get('label') or dict(self._fields['node_type']._description_selection(self.env)).get(
            node.get('type'), '')

    def _close(self, state, port=None, message=None):
        vals = {'state': state, 'date_end': fields.Datetime.now()}
        if port:
            vals['port'] = port
        if message:
            vals['message'] = message
        self.write(vals)
