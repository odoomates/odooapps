from odoo.tests import TransactionCase, tagged

from odoo.addons.om_automation_studio.tools import check_graph
from odoo.addons.om_account_automation.tools import TEMPLATES


@tagged('post_install', '-at_install')
class TestAccountTemplates(TransactionCase):

    def test_templates_are_ready_to_run(self):
        Template = self.env['om.workflow.template']
        for key, model, builder in TEMPLATES:
            if model not in self.env:
                continue
            with self.subTest(template=key):
                name, _description, graph = builder(self.env)
                errors = [issue for issue in check_graph(self.env, model, graph) if issue['level'] == 'error']
                self.assertFalse(errors, f'{key}: {errors}')
                template = Template.search([('name', '=', name), ('model', '=', model)], limit=1)
                self.assertTrue(template, f'{key} is among the templates')
                template.create_workflow()
                self.assertTrue(self.env['om.workflow'].search([('name', '=', name), ('model', '=', model)]))
