from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.om_automation_studio.models.om_workflow_demo import DEMO_PARAM
from odoo.addons.om_automation_studio.tools import PATTERNS, PRESETS, check_graph


@tagged('post_install', '-at_install')
class TestTemplate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Workflow = cls.env['om.workflow']

    def errors(self, model, graph):
        return [issue['message'] for issue in check_graph(self.env, model, graph) if issue['level'] == 'error']

    def filled(self, setup):
        """ The values of a template setup, its empty choices taken from the
        first option, as a user would. """
        values = dict(setup['values'])
        slots = {slot['name']: slot for slot in setup['slots']}
        for slot in setup['slots']:
            if values[slot['name']] not in ([], False) or not slot['required']:
                continue
            if slot['type'] == 'fields':
                values[slot['name']] = [slot['options'][0]['name']]
            elif slot['type'] == 'values':
                field = next(option for option in slots[slot['of']]['options']
                             if option['name'] == values[slot['of']])
                if field['selection']:
                    values[slot['name']] = [field['selection'][0][0]]
                else:
                    values[slot['name']] = self.env[field['relation']].search([], limit=1).ids
        return values

    def test_every_template_on_every_model(self):
        """ Each template builds a chart that could be published, on each
        model it offers, with what it guesses. """
        for key in PATTERNS:
            models = self.Workflow.template_models(key)
            self.assertTrue(models, key)
            for item in models:
                with self.subTest(template=key, model=item['model']):
                    setup = self.Workflow.template_setup(key, item['model'])
                    values = self.filled(setup)
                    if any(not values[slot['name']] for slot in setup['slots']
                           if slot['type'] == 'values' and slot['required']):
                        continue  # a status with no value at all
                    preview = self.Workflow.template_preview(key, item['model'], values)
                    self.assertFalse(preview['missing'])
                    self.assertFalse(self.errors(item['model'], preview['graph']))

    def test_presets(self):
        for (key, model), (__, name, __) in PRESETS.items():
            if model not in self.env:
                continue
            with self.subTest(preset=name):
                setup = self.Workflow.template_setup(key, model)
                self.assertEqual(setup['name'], name)
                preview = self.Workflow.template_preview(key, model, setup['values'])
                self.assertFalse(preview['missing'], name)
                self.assertFalse(self.errors(model, preview['graph']), name)
                self.assertIn(model, [item['model'] for item in self.Workflow.template_models(key)
                                      if item['preset']])

    def test_create_opens_the_designer(self):
        values = {'fields': ['email', 'phone'], 'days': 3}
        action = self.Workflow.template_create('missing_info', 'res.partner', values, 'Complete Contacts')
        workflow = self.Workflow.browse(action['params']['workflow_id'])
        self.assertEqual(action['tag'], 'om_automation_studio')
        self.assertEqual((workflow.name, workflow.model, workflow.state), ('Complete Contacts', 'res.partner', 'draft'))
        wait = next(node for node in workflow.graph['nodes'] if node['type'] == 'wait')
        self.assertEqual(wait['config']['amount'], 3)
        self.assertFalse(self.errors('res.partner', workflow.graph))

    def test_missing_settings(self):
        preview = self.Workflow.template_preview('missing_info', 'res.partner', {'fields': []})
        self.assertFalse(preview['graph'])
        self.assertEqual(preview['missing'], ['Fields to fill'])
        with self.assertRaises(UserError):
            self.Workflow.template_create('missing_info', 'res.partner', {'fields': []})

    def test_values_are_checked(self):
        """ Only the fields a slot offers end in the chart. """
        preview = self.Workflow.template_preview('missing_info', 'res.partner', {
            'fields': ['email', 'password', 'no_such_field'], 'condition': "[('x', '=', __import__('os'))]",
        })
        condition = next(node for node in preview['graph']['nodes'] if node['id'] == 'empty')
        self.assertEqual(condition['config']['domain'], repr([('email', '=', False)]))
        start = next(node for node in preview['graph']['nodes'] if node['type'] == 'start')
        self.assertEqual(start['config']['domain'], '[]')
        with self.assertRaises(UserError):
            self.Workflow.template_setup('missing_info', 'om.workflow')
        with self.assertRaises(UserError):
            self.Workflow.template_setup('no_such_template', 'res.partner')

    def test_only_admin_uses_templates(self):
        user = new_test_user(self.env, 'om_wd_template_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Workflow.with_user(user).template_list()

    def test_each_app_once(self):
        """ An app gets its demo workflows once: the deleted ones stay deleted. """
        param = self.env['ir.config_parameter']
        param.set_str(DEMO_PARAM, '')
        before = self.Workflow.search_count([])
        self.Workflow._load_demo_workflows()
        presets = [preset for (__, model), preset in PRESETS.items() if model in self.env]
        self.assertEqual(self.Workflow.search_count([]) - before, len(presets))
        self.assertEqual(set(param.get_str(DEMO_PARAM).split(',')), {preset[0] for preset in presets})
        approvals = self.Workflow.search([('name', 'in', [preset[1] for preset in presets])])
        approver_ids = {node['config'].get('user_id') for workflow in approvals for node in workflow.graph['nodes']
                        if node['type'] == 'approval'}
        self.assertLessEqual(approver_ids, {self.env.ref('base.user_admin').id})
        self.Workflow._load_demo_workflows()
        self.assertEqual(self.Workflow.search_count([]) - before, len(presets))
