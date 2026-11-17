from odoo import _, api, fields, models


class OmConnectorBackendMixin(models.AbstractModel):
    """ A connection to an external system: a Shopify store, a WooCommerce site, a marketplace
    account… Its jobs are queued with ``_connector_enqueue`` and shown from its form. """
    _name = 'om.connector.backend.mixin'
    _description = 'Connector Connection'

    connector_job_todo_count = fields.Integer(string='Jobs To Do', compute='_compute_connector_job_counts')
    connector_job_failed_count = fields.Integer(string='Failed Jobs', compute='_compute_connector_job_counts')

    def _compute_connector_job_counts(self):
        counts = {
            (backend_id, state): count
            for backend_id, state, count in self.env['om.connector.job'].sudo()._read_group(
                [('backend_model', '=', self._name), ('backend_id', 'in', self.ids),
                 ('state', 'in', ('pending', 'failed'))],
                ['backend_id', 'state'], ['__count'])
        }
        for backend in self:
            backend.connector_job_todo_count = counts.get((backend.id, 'pending'), 0)
            backend.connector_job_failed_count = counts.get((backend.id, 'failed'), 0)

    def _connector_enqueue(self, method_name, payload=None, **kwargs):
        """ Queue ``method_name`` (on this model, or on ``model_name``) for this connection.
        See ``om.connector.job._enqueue`` for the options. """
        self.ensure_one()
        return self.env['om.connector.job']._enqueue(self, method_name, payload, **kwargs)

    def _connector_enqueue_once(self, method_name, payload=None, **kwargs):
        """ Queue ``method_name`` unless a job of this method is already to do for this connection:
        for the scheduled work (fetch the new orders…), which must not pile up. """
        self.ensure_one()
        pending = self.env['om.connector.job'].sudo().search(
            self._connector_job_domain() + [('method_name', '=', method_name), ('state', '=', 'pending')], limit=1)
        return pending or self._connector_enqueue(method_name, payload, **kwargs)

    def _connector_job_failed(self, job):
        """ Called when ``job`` of this connection fails for good. """

    def _connector_job_domain(self):
        return [('backend_model', '=', self._name), ('backend_id', 'in', self.ids)]

    def action_open_connector_jobs(self):
        action = self.env['ir.actions.act_window']._for_xml_id('om_connector_base.om_connector_job_action')
        action['domain'] = self._connector_job_domain()
        action['context'] = {'search_default_filter_todo_failed': 1}
        if len(self) == 1:
            action['display_name'] = _("Jobs of %(connection)s", connection=self.display_name)
        return action

    def unlink(self):
        self.env['om.connector.job'].sudo().search(self._connector_job_domain()).unlink()
        return super().unlink()
