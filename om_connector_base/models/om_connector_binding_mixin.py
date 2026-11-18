from odoo import api, fields, models


class OmConnectorBindingMixin(models.AbstractModel):
    """ The link between a record of an external system and an Odoo record, for one connection:
    a Shopify product and an Odoo product, a Shopify order and a sale order…

    A model that inherits it has a Many2one to its connection, named by ``_connector_backend_field``,
    and a Many2one to the Odoo record, named by ``_connector_record_field``. An external ID is linked
    once per connection.
    """
    _name = 'om.connector.binding.mixin'
    _description = 'Connector Mapping'
    _connector_backend_field = 'backend_id'
    _connector_record_field = 'record_id'

    external_id = fields.Char(string='External ID', required=True, index=True, readonly=True)
    sync_date = fields.Datetime(string='Last Sync', readonly=True)

    @api.model
    def _connector_find(self, backend, external_ids):
        """ The bindings of ``backend`` for one external ID or a list of them. """
        if isinstance(external_ids, (str, int)):
            external_ids = [external_ids]
        return self.search([(self._connector_backend_field, '=', backend.id),
                            ('external_id', 'in', [str(x) for x in external_ids])])

    @api.model
    def _connector_bind(self, backend, external_id, record, vals=None):
        """ Link ``external_id`` to ``record`` for ``backend``, creating or updating the binding. """
        # an archived binding too: the external ID is unique per backend
        binding = self.with_context(active_test=False)._connector_find(backend, external_id)
        values = {self._connector_record_field: record.id, 'sync_date': fields.Datetime.now(), **(vals or {})}
        if binding:
            binding.write(values)
            return binding
        return self.create({self._connector_backend_field: backend.id, 'external_id': str(external_id), **values})
