from odoo import api, models

from odoo.addons.om_account_automation.tools import TEMPLATES

# the templates added so far: each once, so that the deleted ones stay deleted
LOADED_PARAM = 'om_account_automation.loaded_templates'
# the modules whose installation brings templates
APPS = {'om_account_automation', 'account', 'om_account_pdc'}


class OmWorkflowTemplate(models.Model):
    _inherit = 'om.workflow.template'

    def _register_hook(self):
        """ Once every module is loaded, those installed after this one too: the templates of the models just
            installed, e.g. the cheques of Post-dated Cheques. """
        super()._register_hook()
        if APPS & set(self.pool.updated_modules):
            self._om_account_load_templates()

    @api.model
    def _om_account_load_templates(self):
        """ The accounting templates of the installed models, shared by every company: each added once.

        :return: the keys of the templates added
        """
        param = self.env['ir.config_parameter'].sudo()
        done = set(filter(None, (param.get_str(LOADED_PARAM) or '').split(',')))
        added = []
        for key, model, builder in TEMPLATES:
            if key in done or model not in self.env:
                continue
            name, description, graph = builder(self.env)
            self.sudo().create({
                'name': name,
                'description': description,
                'model_id': self.env['ir.model']._get_id(model),
                'graph': graph,
                'company_id': False,
            })
            added.append(key)
        if added:
            param.set_str(LOADED_PARAM, ','.join(sorted(done | set(added))))
        return added
