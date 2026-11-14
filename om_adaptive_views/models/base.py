from odoo import api, models

ADAPTED_VIEWS = ('form', 'list', 'search')


class Base(models.AbstractModel):
    _inherit = 'base'

    def _om_adaptable(self, view_type):
        return (view_type in ADAPTED_VIEWS and not self._name.startswith(('om.adapt', 'om.usage'))
                and 'om.adapt.rule' in self.env)

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        """ Views are cached; what is applied for the current user is part of the key. """
        key = super()._get_view_cache_key(view_id, view_type, **options)
        if not self._om_adaptable(view_type):
            return key
        if self.env.context.get('om_adapt_raw'):
            return key + ('om_adapt_raw',)
        return key + self.env['om.adapt.rule']._om_view_cache_key()

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ Apply the changes applied for the current user while the view is built.

        Nothing is written in the views: undoing a change only needs the view to be built
        again, which the version in the cache key takes care of.
        """
        arch, view = super()._get_view(view_id, view_type, **options)
        if not self._om_adaptable(view_type) or self.env.context.get('om_adapt_raw'):
            return arch, view
        Rules = self.env['om.adapt.rule']
        rules = Rules._om_applied(self._name, view_type, view.id if view else False)
        if rules:
            Rules._om_apply_arch(arch, view_type, rules)
        return arch, view
