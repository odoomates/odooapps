from markupsafe import Markup

from odoo import api, fields, models
from odoo.fields import Domain


class ApprovalSimulate(models.TransientModel):
    """ What a flow would do for a record, without asking anything: whether it applies, the steps and who approves
    them, and whether the record would be locked. """
    _name = 'approval.simulate'
    _description = 'Test an Approval Flow'

    flow_id = fields.Many2one('approval.rule', required=True, ondelete='cascade')
    model = fields.Char(related='flow_id.model')
    model_id = fields.Many2one(related='flow_id.model_id')
    record_ref = fields.Reference(selection='_selection_record_ref', string='Record')
    user_id = fields.Many2one('res.users', string='Asked By', required=True, default=lambda self: self.env.user,
                              domain=[('share', '=', False)],
                              help='Who clicks the button, or submits the document.')
    result = fields.Html(compute='_compute_result', sanitize=False)

    @api.model
    def _selection_record_ref(self):
        flows = self.env['approval.rule'].sudo().with_context(active_test=False).search([('model_id', '!=', False)])
        return [(model.model, model.name) for model in flows.model_id]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        flow = self.env['approval.rule'].browse(values.get('flow_id') or self.env.context.get('default_flow_id'))
        if 'record_ref' in fields_list and flow.exists() and flow.model in self.env and not values.get('record_ref'):
            record = self.env[flow.model].search(Domain(flow._literal_domain()), limit=1) \
                or self.env[flow.model].search([], limit=1)
            if record:
                values['record_ref'] = '%s,%s' % (record._name, record.id)
        return values

    @api.depends('flow_id', 'record_ref', 'user_id')
    def _compute_result(self):
        for wizard in self:
            record = wizard.record_ref
            if not wizard.flow_id or not record or record._name != wizard.flow_id.model:
                wizard.result = Markup('<p class="text-muted">%s</p>') % self.env._(
                    'Choose a %s to see what the flow does for it.', wizard.flow_id.model_id.name or '')
                continue
            wizard.result = wizard.flow_id.with_user(wizard.user_id).sudo()._simulate(record.sudo())
