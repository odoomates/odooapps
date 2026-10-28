# Hide Activities for some data: the screens, the systray, and what a client
# schedules or changes there.
from lxml import etree

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestActivities(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = 'om-access-manager-activities-pw'
        cls.user = new_test_user(cls.env, 'om_access_activities_user',
                                 groups='base.group_user,base.group_partner_manager', password=cls.password)
        cls.partner = cls.env['res.partner'].create({'name': 'Busy'})
        cls.todo = cls.env.ref('mail.mail_activity_data_todo')
        cls.activity = cls.partner.activity_schedule(
            'mail.mail_activity_data_todo', summary='Call back', user_id=cls.user.id)
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'No Activities on Contacts',
            'user_ids': [(6, 0, cls.user.ids)],
            'model_ids': [(0, 0, {'model_id': cls.env['ir.model']._get('res.partner').id, 'hide_activities': True})],
        })

    def _call(self, model, method, args, kwargs=None, route='call_kw'):
        return self.make_jsonrpc_request(f'/web/dataset/{route}/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def test_the_screens_lose_the_activities(self):
        Partner = self.env['res.partner'].with_user(self.user)
        result = Partner.get_views([(False, 'form'), (False, 'list')])
        self.assertFalse(result['models']['res.partner'].get('has_activities'))
        form = etree.fromstring(result['views']['form']['arch'])
        self.assertIn('o_om_hide_activities', (form.get('class') or '').split())
        self.assertFalse(etree.fromstring(result['views']['list']['arch']).xpath(
            "//field[@name='activity_ids' or @widget='list_activity']"))
        action = self.env['om.access.profile'].with_user(self.user)._filter_action_views({
            'type': 'ir.actions.act_window', 'res_model': 'res.partner',
            'views': [[False, 'list'], [False, 'activity']], 'view_mode': 'list,activity',
        })
        self.assertEqual(action['view_mode'], 'list')
        # the systray leaves the data out
        groups = self.env['res.users'].with_user(self.user)._get_activity_groups()
        self.assertNotIn('res.partner', [group['model'] for group in groups])

    def test_other_users_keep_them(self):
        self.profile.user_ids = [(5,)]
        result = self.env['res.partner'].with_user(self.user).get_views([(False, 'form')])
        self.assertTrue(result['models']['res.partner'].get('has_activities'))
        groups = self.env['res.users'].with_user(self.user)._get_activity_groups()
        self.assertIn('res.partner', [group['model'] for group in groups])

    @mute_logger('odoo.http')
    def test_a_client_cannot_schedule_change_or_close_them(self):
        self.authenticate(self.user.login, self.password)
        with self.assertRaises(JsonRpcException):
            self._call('mail.activity', 'create', [{
                'res_model_id': self.env['ir.model']._get_id('res.partner'), 'res_id': self.partner.id,
                'activity_type_id': self.todo.id, 'user_id': self.user.id,
            }])
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'activity_schedule', [self.partner.ids], {'summary': 'Again'})
        with self.assertRaises(JsonRpcException):
            self._call('mail.activity', 'write', [self.activity.ids, {'summary': 'Changed'}])
        with self.assertRaises(JsonRpcException):
            self._call('mail.activity', 'action_feedback', [self.activity.ids], route='call_button')
        wizard = self.env['mail.activity.schedule'].with_user(self.user).with_context(
            active_model='res.partner', active_ids=self.partner.ids).create({'activity_type_id': self.todo.id})
        with self.assertRaises(JsonRpcException):
            self._call('mail.activity.schedule', 'action_schedule_activities', [wizard.ids], route='call_button')
        self.assertEqual(self.activity.summary, 'Call back')
        self.assertTrue(self.activity.exists())

    def test_odoo_itself_still_schedules_them(self):
        activity = self.partner.with_user(self.user).activity_schedule('mail.mail_activity_data_todo')
        self.assertTrue(activity)
        activity.action_feedback(feedback='Done by the code')
        # a done activity is archived or deleted, depending on its type
        self.assertFalse(activity.exists() and activity.active)

    def test_the_other_data_keep_their_activities(self):
        # without other apps, Odoo 18 has activities on the contacts and little else:
        # the profile hides those of another data, and the contacts are the other data
        self.profile.model_ids.model_id = self.env['ir.model']._get('ir.actions.server')
        self.authenticate(self.user.login, self.password)
        partner_activity = self._call('mail.activity', 'create', [{
            'res_model_id': self.env['ir.model']._get_id('res.partner'), 'res_id': self.partner.id,
            'activity_type_id': self.todo.id, 'user_id': self.user.id,
        }])
        self.assertTrue(partner_activity)

    def test_the_chatter_has_no_activity_button(self):
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            for (let tries = 0; tries < 75 && !document.querySelector('.o-mail-Chatter-sendMessage'); tries++) {
                await wait(200);
            }
            if (!document.querySelector('.o-mail-Chatter-sendMessage')) {
                throw new Error('no chatter');
            }
            if (document.querySelector('.o-mail-Chatter-activity, .o-mail-ActivityList')) {
                throw new Error('the activities are shown');
            }
            console.log('test successful');
        })()"""
        self.browser_js(f'/odoo/action-base.action_partner_form/{self.partner.id}', code,
                        login=self.user.login, timeout=90)
