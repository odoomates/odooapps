import logging

from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.om_automation_studio.tools import PATTERNS, PRESETS
from odoo.addons.om_automation_studio.tools.templates import preset_values

_logger = logging.getLogger(__name__)

# the apps done so far, so that each gets its demo workflows once
DEMO_PARAM = 'om_automation_studio.demo_apps'


class OmWorkflow(models.Model):
    _inherit = 'om.workflow'

    def _register_hook(self):
        """ Once every module is loaded, those installed after this one
        too: the demo workflows of the apps just installed. """
        super()._register_hook()
        apps = {preset[0] for preset in PRESETS.values()} | {'om_automation_studio'}
        if apps & set(self.pool.updated_modules) and self.env['ir.module.module']._get('om_automation_studio').demo:
            self._load_demo_workflows()

    @api.model
    def _load_demo_workflows(self):
        """ The presets of the templates as draft workflows, for the apps the
        database has, each app once, so that the deleted ones stay deleted. """
        param = self.env['ir.config_parameter'].sudo()
        done = set(filter(None, (param.get_param(DEMO_PARAM) or '').split(',')))
        loaded = set()
        admin = self.env.ref('base.user_admin').id
        for (key, model), (app, __, __) in PRESETS.items():
            if app in done or model not in self.env:
                continue
            values = preset_values(self.env, key, model)
            # the approvers and managers of the demo: the administrator, not the superuser
            for slot in PATTERNS[key].slots(self.env, self.env[model]):
                if slot['type'] == 'user' and slot['default'].get('mode') == 'user':
                    values.setdefault(slot['name'], {'mode': 'user', 'id': admin})
            try:
                self.sudo()._template_create(key, model, values)
            except UserError:
                # a database without what the preset needs, such as a won stage: no demo of it
                _logger.warning("Demo workflow %s skipped", key, exc_info=True)
            loaded.add(app)
        param.set_param(DEMO_PARAM, ','.join(sorted(done | loaded)))
