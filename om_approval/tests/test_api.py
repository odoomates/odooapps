import json
import xmlrpc.client
from datetime import datetime, timedelta

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestApi(HttpCase):
    """ The external APIs ask the approval of a button instead of running it, as the web client does. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_api_user', password='om_api_user',
                                 groups='base.group_user,base.group_partner_manager')
        approver = new_test_user(cls.env, 'om_api_approver')
        button = cls.env['approval.button'].create({
            'model_id': cls.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        cls.flow = cls.env['approval.rule'].create({
            'name': 'Archive', 'model_id': button.model_id.id, 'button_id': button.id, 'request_note': 'optional',
            'step_ids': [Command.create({'name': 'Approver', 'approver_type': 'user',
                                         'user_ids': [Command.link(approver.id)]})],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'API Customer'})

    def requests(self):
        return self.env['approval.request'].search([('res_model', '=', 'res.partner'),
                                                    ('res_id', '=', self.partner.id)])

    @mute_logger('odoo.addons.rpc.controllers.xmlrpc')
    def test_xmlrpc(self):
        result = self.xmlrpc_object.execute_kw(
            self.env.cr.dbname, self.user.id, 'om_api_user', 'res.partner', 'action_archive', [[self.partner.id]])
        self.assertEqual(result['tag'], 'display_notification')
        self.assertTrue(self.partner.active)
        self.assertEqual(self.requests().state, 'to_approve')
        # an ordinary call is not stopped
        self.assertTrue(self.xmlrpc_object.execute_kw(
            self.env.cr.dbname, self.user.id, 'om_api_user', 'res.partner', 'read', [[self.partner.id], ['name']]))

    def test_xmlrpc_note_required(self):
        self.flow.request_note = 'required'
        with mute_logger('odoo.http', 'odoo.addons.rpc.controllers.xmlrpc'), \
                self.assertRaises(xmlrpc.client.Fault):
            self.xmlrpc_object.execute_kw(
                self.env.cr.dbname, self.user.id, 'om_api_user', 'res.partner', 'action_archive', [[self.partner.id]])
        self.assertFalse(self.requests())

    def test_json2(self):
        key = self.env['res.users.apikeys'].with_user(self.user)._generate(
            scope='rpc', name='test', expiration_date=datetime.now() + timedelta(days=1))
        response = self.url_open('/json/2/res.partner/action_archive', data=json.dumps({'ids': [self.partner.id]}),
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['tag'], 'display_notification')
        self.assertTrue(self.partner.active)
        self.assertEqual(self.requests().state, 'to_approve')
