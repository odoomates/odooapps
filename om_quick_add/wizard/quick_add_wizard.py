from odoo import api, fields, models

from ..models.quick_add_mixin import clean_context


class OmQuickAddWizard(models.AbstractModel):
    """What the Quick Add dialogs share: the document they add to."""
    _name = 'om.quick.add.wizard'
    _description = 'Quick Add Dialog'

    res_model = fields.Char(required=True, readonly=True)
    res_id = fields.Many2oneReference(model_field='res_model', required=True, readonly=True)
    has_prices = fields.Boolean(compute='_compute_has_prices')
    document_name = fields.Char(compute='_compute_document_name')

    @api.depends('res_model')
    def _compute_has_prices(self):
        for wizard in self:
            wizard.has_prices = bool(wizard.res_model) and self.env[wizard.res_model]._om_qa_has_prices

    @api.depends('res_model', 'res_id')
    def _compute_document_name(self):
        for wizard in self:
            wizard.document_name = wizard._om_qa_document().display_name if wizard.res_model else False

    def _om_qa_document(self):
        """The document, without the context the client carries over from the list of lines of the form."""
        self.ensure_one()
        return self.env[self.res_model].with_context(clean_context(self.env.context)).browse(self.res_id)

    def _om_qa_load(self):
        """Fill the dialog when it opens."""

    def _om_qa_action(self, title=None):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title or self.env._("Quick Add"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': clean_context(self.env.context),
        }

    def _om_qa_add_and_close(self, items):
        added, raised = self._om_qa_document()._om_qa_add(items)
        parts = []
        if added:
            parts.append(self.env._("%s product(s) added", added))
        if raised:
            parts.append(self.env._("%s quantity(ies) raised", raised))
        message = ", ".join(parts) + "." if parts else self.env._("Nothing to add.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
