from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMultiCompany(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Approvals Company B'})
        cls.user_a = new_test_user(cls.env, 'om_mc_approval_a', groups='base.group_user',
                                   company_id=cls.company_a.id, company_ids=[Command.set(cls.company_a.ids)])
        cls.user_b = new_test_user(cls.env, 'om_mc_approval_b', groups='base.group_user',
                                   company_id=cls.company_b.id, company_ids=[Command.set(cls.company_b.ids)])
        button = cls.env['approval.button'].create({
            'model_id': cls.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        Flow = cls.env['approval.rule']
        values = {'model_id': cls.env['ir.model']._get_id('res.partner'), 'button_id': button.id}
        cls.flow_b = Flow.create(dict(values, name='Archive in B', company_id=cls.company_b.id))
        cls.flow_shared = Flow.create(dict(values, name='Archive anywhere'))

    def test_flows(self):
        self.assertIn(self.flow_shared, self.env['approval.rule'].with_user(self.user_a).search([]),
                      'a flow without company is shared')
        self.assertNotIn(self.flow_b, self.env['approval.rule'].with_user(self.user_a).search([]))
        self.assertEqual(self.flow_b.with_user(self.user_b).name, 'Archive in B')
        with self.assertRaises(AccessError):
            self.flow_b.with_user(self.user_a).read(['name'])

    def test_requests_and_their_lines(self):
        partner = self.env['res.partner'].create({'name': 'Customer of B', 'company_id': self.company_b.id})
        Request = self.env['approval.request']
        with self.assertRaises(UserError):
            Request.create({'name': 'Mixed', 'res_model': 'res.partner', 'res_id': partner.id,
                            'requester_id': self.user_a.id, 'company_id': self.company_a.id,
                            'flow_id': self.flow_b.id})
        request = Request.create({'name': 'In B', 'res_model': 'res.partner', 'res_id': partner.id,
                                  'requester_id': self.user_b.id, 'company_id': self.company_b.id,
                                  'flow_id': self.flow_b.id})
        line = self.env['approval.line'].create({'request_id': request.id, 'name': 'Approve',
                                                 'approver_user_ids': [Command.set((self.user_a | self.user_b).ids)]})
        self.assertEqual(line.company_id, self.company_b, 'the approval follows its request')
        self.assertFalse(self.env['approval.line'].with_user(self.user_a).search([('id', '=', line.id)]))
        self.assertEqual(self.env['approval.line'].with_user(self.user_b).search([('id', '=', line.id)]), line)
        with self.assertRaises(AccessError):
            request.with_user(self.user_a).read(['name'])
