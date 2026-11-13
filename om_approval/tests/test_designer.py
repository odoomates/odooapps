from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.om_approval.models import approval_designer

from .test_button_rule import ApprovalCase

# res.partner as a template knows it, in the tests
PARTNER_PRESET = {
    'label': 'Contacts', 'amount': 'color', 'limit': 5, 'high_limit': 9, 'confirm': 'action_archive',
    'cancel': 'action_archive', 'cancel_domain': [('active', '=', True)], 'responsible': 'user_id',
}


@tagged('post_install', '-at_install')
class TestDesigner(ApprovalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, 'om_designer_manager',
                                    groups='base.group_user,om_approval.group_approval_manager')
        cls.Rule = cls.env['approval.rule'].with_user(cls.manager)

    def test_load(self):
        data = self.Rule.designer_load(self.flow.id)
        flow = data['flow']
        self.assertEqual((flow['id'], flow['model'], flow['button_id']), (self.flow.id, 'res.partner', self.button.id))
        self.assertEqual(flow['steps'][0]['group_id'], self.approvers.id)
        self.assertIn(self.button.id, [button['id'] for button in data['buttons']])
        self.assertIn(('field', 'Person on the Record'), [tuple(choice) for choice in data['approver_types']])
        self.assertIn('Partner Approvers', str(data['preview']['summary']))
        self.assertEqual(data['preview']['steps'][0]['who'], 'users of the group Partner Approvers')

    def test_load_new(self):
        data = self.Rule.designer_load(False, 'res.partner')
        self.assertFalse(data['flow']['id'])
        self.assertFalse(data['flow']['active'], 'a flow made in the designer starts inactive')
        self.assertEqual(data['flow']['steps'], [])
        self.assertEqual(data['step_defaults']['domain'], '[]')

    def test_save_steps_in_order(self):
        flow = self.Rule.designer_load(self.flow.id)['flow']
        director = dict(self.Rule.designer_load(self.flow.id)['step_defaults'],
                        name='Director', approver_type='user', user_ids=[self.director.id])
        flow['steps'].insert(0, director)
        flow['name'] = 'Archive a big partner'
        flow['domain'] = '[["name", "ilike", "Big"]]'
        saved = self.Rule.designer_save(self.flow.id, flow)['flow']
        self.assertEqual([step['name'] for step in saved['steps']], ['Director', 'Approvers'])
        self.assertEqual(self.flow.name, 'Archive a big partner')
        self.assertEqual(self.flow.step_ids.sorted('sequence').mapped('name'), ['Director', 'Approvers'])
        # remove the first step: it is deleted, the other kept
        kept = self.flow.step_ids.filtered(lambda s: s.name == 'Approvers')
        saved['steps'].pop(0)
        self.Rule.designer_save(self.flow.id, saved)
        self.assertEqual(self.flow.step_ids, kept)

    def test_save_new_and_activate(self):
        data = self.Rule.designer_load(False, 'res.partner')
        flow = dict(data['flow'], name='Archive', button_id=self.button.id)
        flow['steps'] = [dict(data['step_defaults'], name='Salesperson', approver_type='field', field_path='user_id')]
        saved = self.Rule.designer_save(False, flow)['flow']
        rule = self.env['approval.rule'].with_context(active_test=False).browse(saved['id'])
        self.assertFalse(rule.active)
        self.assertEqual(rule.step_ids.field_path, 'user_id')
        self.Rule.designer_set_active(rule.id, True)
        self.assertTrue(rule.active)

    def test_save_checks_the_flow(self):
        flow = self.Rule.designer_load(self.flow.id)['flow']
        flow['steps'][0].update(approver_type='field', field_path='name')
        with self.assertRaises(ValidationError):
            self.Rule.designer_save(self.flow.id, flow)

    def test_preview_of_an_unsaved_flow(self):
        flow = self.Rule.designer_load(self.flow.id)['flow']
        flow['steps'][0].update(approver_type='user', user_ids=[self.director.id], domain='[["name", "=", "X"]]')
        preview = self.Rule.designer_preview(flow)
        self.assertEqual(preview['steps'][0]['who'], self.director.name)
        self.assertIn('Name = X', str(preview['steps'][0]['when']))
        self.assertEqual(self.flow.step_ids.approver_type, 'group', 'previewing saves nothing')
        # a path being typed is shown as it is
        flow['steps'][0].update(approver_type='field', field_path='no_such_field')
        self.assertIn('the no_such_field of the record', str(self.Rule.designer_preview(flow)['summary']))

    def test_only_managers(self):
        Rule = self.env['approval.rule'].with_user(self.requester)
        calls = (lambda: Rule.designer_load(self.flow.id), lambda: Rule.gallery_load(),
                 lambda: Rule.designer_save(self.flow.id, {}),
                 lambda: Rule.gallery_create('amount', 'res.partner'))
        for call in calls:
            with self.assertRaises(UserError):
                call()

    def test_gallery(self):
        with patch.dict(approval_designer.PRESETS, {'res.partner': PARTNER_PRESET}):
            templates = {t['key']: t for t in self.Rule.gallery_load()['templates']}
            self.assertIn('res.partner', [m['model'] for m in templates['amount']['models']])
            self.assertNotIn('res.partner', [m['model'] for m in templates['discount']['models']])
            flow = self.env['approval.rule'].with_context(active_test=False).browse(
                self.Rule.gallery_create('two_level', 'res.partner'))
        self.assertFalse(flow.active, 'a flow from a template starts inactive')
        self.assertEqual(flow.button_id.method, 'action_archive')
        self.assertEqual((flow.domain, flow.amount_field, flow.amount_min), ('[]', 'color', 5))
        self.assertEqual(flow.step_ids.mapped('approver_type'), ['group', 'user'])
        self.assertEqual(flow.step_ids[1].amount_min, 9, 'the director approves above the higher amount')
        self.assertEqual(flow.step_ids[1].user_ids, self.manager)
        with patch.dict(approval_designer.PRESETS, {'res.partner': PARTNER_PRESET}):
            flow = self.env['approval.rule'].with_context(active_test=False).browse(
                self.Rule.gallery_create('cancel', 'res.partner'))
        self.assertEqual((flow.button_id.method, flow.domain), ('action_archive', "[('active', '=', True)]"))
        with patch.dict(approval_designer.PRESETS, {'res.partner': dict(PARTNER_PRESET, cancel='no_such_button')}):
            with self.assertRaises(UserError):
                self.Rule.gallery_create('cancel', 'res.partner')

    def test_gallery_refuses_what_does_not_fit(self):
        with self.assertRaises(UserError):
            self.Rule.gallery_create('discount', 'res.partner')
        self.assertFalse(self.Rule.gallery_load(prefix='nothing.')['templates'])

    def test_demo_flows(self):
        """ The demo flows of an app: made once, inactive, the administrator as the director. """
        Rule = self.env['approval.rule'].with_context(active_test=False)
        with patch.dict(approval_designer.PRESETS, {'res.partner': PARTNER_PRESET}), \
                patch.dict(approval_designer.DEMO_FLOWS, {'res.partner': ('om_demo_app', ['two_level', 'cancel'])},
                           clear=True):
            before = Rule.search([])
            self.assertEqual(Rule._load_demo_flows(), {'om_demo_app'})
            flows = Rule.search([]) - before
            self.assertEqual(len(flows), 2)
            self.assertFalse(any(flows.mapped('active')), 'demo flows wait to be activated')
            director = flows.step_ids.filtered(lambda s: s.approver_type == 'user')
            self.assertEqual(director.user_ids, self.env.ref('base.user_admin'))
            flows[0].unlink()
            self.assertFalse(Rule._load_demo_flows(), 'each app once: a deleted demo flow stays deleted')
            self.assertEqual(len(Rule.search([]) - before), 1)

    def test_open_designer(self):
        action = self.flow.action_open_designer()
        self.assertEqual((action['tag'], action['params']), ('om_approval_designer', {'flow_id': self.flow.id}))


@tagged('post_install', '-at_install')
class TestDesignerTour(HttpCase):

    def test_designer(self):
        """ Open a flow in the designer, add a step for given people, save and activate it. """
        button = self.env['approval.button'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        group = self.env['res.groups'].create({'name': 'Tour Group'})
        flow = self.env['approval.rule'].create({
            'name': 'Tour Flow', 'model_id': button.model_id.id, 'button_id': button.id, 'active': False,
            'step_ids': [Command.create({'name': 'First', 'approver_type': 'group', 'group_id': group.id})],
        })
        self.start_tour(f'/odoo/action-om_approval.om_approval_flow_action/{flow.id}', 'om_approval_designer',
                        login='admin')
        self.assertTrue(flow.active)
        self.assertEqual(flow.step_ids.sorted('sequence').mapped('name'), ['First', 'Tour Step'])
        self.assertEqual(flow.step_ids.sorted('sequence')[1].user_ids, self.env.ref('base.user_admin'))
        self.assertEqual(flow.step_ids.sorted('sequence')[1].remind_days, 2)
        self.assertEqual(flow.step_ids.sorted('sequence')[1].approval_mode, 'all')
