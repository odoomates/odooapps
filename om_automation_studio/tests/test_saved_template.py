import base64
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import WorkflowCase, chain, node


@tagged('post_install', '-at_install')
class TestSavedTemplate(WorkflowCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env['om.workflow.template']
        cls.admin = cls.env.ref('base.user_admin')
        cls.todo = cls.env.ref('mail.mail_activity_data_todo')
        # a record without external id: found again by its name
        cls.vip = cls.env['res.partner.category'].create({'name': 'Template VIP'})
        cls.graph = chain(
            node('s', 'start', trigger='manual'),
            node('a', 'activity', activity_type_id=cls.todo.id, assign='user', user_id=cls.admin.id,
                 summary='Call {{ object.name }}', days=0),
            node('u', 'update', values=[
                {'field': 'user_id', 'mode': 'value', 'value': cls.admin.id},
                {'field': 'category_id', 'mode': 'value', 'value': [cls.vip.id]},
            ]),
            node('end', 'end'),
        )
        cls.workflow = cls.make_workflow(cls, cls.graph, publish=False, description='Calls new contacts')

    def save_as_template(self, workflow):
        action = workflow.action_save_as_template()
        return self.Template.with_context(action['context']).create({})

    def test_save_and_start_from_it(self):
        template = self.save_as_template(self.workflow)
        self.assertEqual((template.name, template.model, template.description),
                         ('Test Workflow', 'res.partner', 'Calls new contacts'))
        self.assertEqual(template.graph, self.graph)
        self.assertIn(template.id, [item['id'] for item in self.Template.gallery_list()])
        action = template.create_workflow('From the Template')
        workflow = self.Workflow.browse(action['params']['workflow_id'])
        self.assertEqual((workflow.name, workflow.state, workflow.graph), ('From the Template', 'draft', self.graph))

    def test_export_and_import(self):
        template = self.save_as_template(self.workflow)
        data = json.loads(base64.b64decode(template.export_file))
        activity = data['graph']['nodes'][1]['config']
        self.assertEqual(activity['user_id'], {'__ref__': 'base.user_admin', 'name': self.admin.display_name})
        self.assertEqual(activity['activity_type_id']['__ref__'], 'mail.mail_activity_data_todo')
        self.assertEqual(data['graph']['nodes'][2]['config']['values'][1]['value'],
                         [{'__ref__': False, 'name': 'Template VIP'}])
        # back in a database: the same records, by external id or by name
        wizard = self.env['om.workflow.template.import'].create({
            'file': base64.b64encode(json.dumps(data).encode()).decode(), 'filename': 'call.json'})
        imported = self.Template.browse(wizard.action_import()['res_id'])
        self.assertEqual(imported.graph, self.graph)
        self.assertFalse(imported.import_note)

    def test_import_what_is_missing(self):
        data = self.save_as_template(self.workflow)._export_data()
        data['graph']['nodes'][1]['config']['user_id'] = {'__ref__': 'other_db.user_boss', 'name': 'The Boss'}
        imported = self.Template._import_data(data)
        self.assertFalse(imported.graph['nodes'][1]['config']['user_id'])
        self.assertIn('The Boss', imported.import_note)
        # the designer points it out
        workflow = self.Workflow.browse(imported.create_workflow()['params']['workflow_id'])
        self.assertTrue(workflow.designer_load()['issues'])

    def test_bad_files(self):
        data = self.save_as_template(self.workflow)._export_data()
        for wrong in ({**data, 'format': 'other'}, {**data, 'version': 99}, {**data, 'model': 'no.such.model'},
                      {**data, 'graph': {'nodes': 'x'}}, ['not', 'a', 'dict']):
            with self.subTest(wrong=wrong), self.assertRaises(UserError):
                self.Template._import_data(wrong)
        wizard = self.env['om.workflow.template.import'].create({'file': base64.b64encode(b'not json').decode()})
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_company_templates(self):
        other = self.env['res.company'].create({'name': 'Other Company'})
        mine = self.save_as_template(self.workflow)
        theirs = self.save_as_template(self.workflow)
        theirs.company_id = other
        shared = self.save_as_template(self.workflow)
        shared.company_id = False
        admin = new_test_user(self.env, 'om_wd_template_admin', groups='base.group_system')
        visible = self.Template.with_user(admin).search([]).ids
        self.assertIn(mine.id, visible)
        self.assertIn(shared.id, visible)
        self.assertNotIn(theirs.id, visible)

    def test_only_admin(self):
        with self.assertRaises(AccessError):
            self.Template.with_user(self.supervisor).create({'name': 'x', 'model_id': self.partner_model.id})
        with self.assertRaises(AccessError):
            self.Template.with_user(self.supervisor).gallery_list()
