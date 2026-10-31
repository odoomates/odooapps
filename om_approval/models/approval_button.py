from lxml import etree

from odoo import api, fields, models

# Not buttons: an approval rule on them would stop the ordinary work of the web client.
NOT_BUTTONS = frozenset({
    'create', 'write', 'unlink', 'web_save', 'web_read', 'web_search_read', 'read', 'search', 'search_read',
    'onchange', 'copy', 'default_get', 'name_search', 'web_name_search',
})


class ApprovalButton(models.Model):
    """ A button of the views of a model calling a method of the model, which an approval rule can stop. """
    _name = 'approval.button'
    _description = 'Approval Button'
    _order = 'model, name, method'
    _rec_names_search = ['name', 'method']

    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', index=True)
    model = fields.Char(related='model_id.model', store=True, string='Model Name')
    method = fields.Char(required=True)
    name = fields.Char(string='Label', required=True)

    _model_method_uniq = models.Constraint('unique(model_id, method)', 'A button is listed once per model.')

    @api.depends('name', 'method')
    def _compute_display_name(self):
        for button in self:
            button.display_name = f'{button.name} ({button.method})'

    @api.model
    def _label(self, node, method):
        """ The label the user sees on the button: its string, its text, the string of the field it shows, as a
            smart button does, or else its method made readable. """
        text = ' '.join(' '.join(node.itertext()).split())
        inner = next((child.get('string') for child in node.iter() if child is not node and child.get('string')), '')
        readable = method.removeprefix('action_').removeprefix('button_').replace('_', ' ').strip().capitalize()
        return node.get('string') or node.get('title') or text or inner or readable or method

    @api.model
    def _sync(self, model_name):
        """ List the buttons calling a method in the form and list views of `model_name`.

        :return: the buttons of the model
        """
        model = self.env['ir.model']._get(model_name)
        if not model or model_name not in self.env:
            return self.browse()
        found = {}
        views = self.env['ir.ui.view'].sudo().search([
            ('model', '=', model_name), ('type', 'in', ('form', 'list')), ('mode', '=', 'primary'),
        ])
        for view in views:
            try:
                arch = self.env[model_name].sudo().get_view(view.id, view.type)['arch']
            except Exception:  # a broken view of another module must not stop the listing
                continue
            for node in etree.fromstring(arch).iter('button'):
                method = node.get('name')
                if node.get('type') != 'object' or not method or method in NOT_BUTTONS:
                    continue
                if not callable(getattr(self.env[model_name], method, None)):
                    continue
                found.setdefault(method, self._label(node, method))
        existing = self.sudo().search([('model_id', '=', model.id)])
        known = set(existing.mapped('method'))
        self.sudo().create([
            {'model_id': model.id, 'method': method, 'name': label}
            for method, label in found.items() if method not in known
        ])
        return self.sudo().search([('model_id', '=', model.id)])
