import base64
import io
from datetime import timedelta

from PIL import Image

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools.binary import BinaryBytes
from odoo.tools.safe_eval import safe_eval

from .common import SIGNATURE, make_pdf
from .test_sign_template import SignTemplateCommon


def png(width=60, height=80):
    with io.BytesIO() as stream:
        Image.new('RGB', (width, height), 'white').save(stream, 'PNG')
        return base64.b64encode(stream.getvalue()).decode()


@tagged('post_install', '-at_install')
class TestSignViews(SignTemplateCommon, TransactionCase):
    """ What the kanban views, the request form and the menus show. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.colleague = new_test_user(cls.env, 'om_sign_colleague', groups='base.group_user,om_sign.group_sign_user',
                                      email='colleague@example.com')
        cls.manager = new_test_user(cls.env, 'om_sign_manager', groups='base.group_user,om_sign.group_sign_manager',
                                    email='manager@example.com')

    # ------------------------------------------------------------------
    # The thumbnail of a template
    # ------------------------------------------------------------------

    def test_thumbnail_kept(self):
        template = self.sign_template.with_user(self.sender)
        checksum = template.document_checksum
        self.assertTrue(checksum, 'the checksum of the attachment of the PDF')
        self.assertFalse(template.thumbnail)
        self.assertTrue(template.save_thumbnail('data:image/png;base64,' + png(), checksum))
        self.assertTrue(template.thumbnail)
        self.assertEqual(Image.open(io.BytesIO(template.thumbnail.content)).size, (60, 80))

    def test_thumbnail_refused(self):
        template = self.sign_template.with_user(self.sender)
        checksum = template.document_checksum
        self.assertFalse(template.save_thumbnail(png(), 'another PDF'), 'drawn from another PDF')
        self.assertFalse(template.save_thumbnail(png(), False))
        self.assertFalse(template.save_thumbnail(base64.b64encode(b'<svg></svg>').decode(), checksum),
                         'an image the browser draws only')
        self.assertFalse(template.save_thumbnail('not base64!', checksum))
        self.assertFalse(template.save_thumbnail(png() + 'A' * 1500000, checksum), 'too large')
        colleague = self.sign_template.with_user(self.colleague)
        self.assertFalse(colleague.has_access('write'))
        self.assertFalse(colleague.save_thumbnail(png(), checksum), 'a user who may not change the template')
        self.assertFalse(self.sign_template.thumbnail)

    def test_thumbnail_cleared_with_the_pdf(self):
        template = self.sign_template.with_user(self.sender)
        template.save_thumbnail(png(), template.document_checksum)
        copy = template.copy()
        self.assertTrue(copy.thumbnail, 'the same PDF, the same picture')
        old_checksum = template.document_checksum
        template.write({'document_file': BinaryBytes(make_pdf(3))})
        self.assertNotEqual(template.document_checksum, old_checksum)
        self.assertFalse(template.thumbnail, 'drawn again from the new PDF')
        self.assertFalse(template.save_thumbnail(png(), old_checksum))
        self.assertTrue(copy.thumbnail)

    # ------------------------------------------------------------------
    # The counts of a template, the cards and the form of a request
    # ------------------------------------------------------------------

    def test_template_counts(self):
        signed = self.send_template()
        for signer in signed.signer_ids:
            signer.sudo()._sign(signer.partner_id.name, SIGNATURE)
        self.send_template()
        # a draft, not counted as sent; the counts are those of the requests the user sees
        self.env['sign.request'].with_user(self.sender).create(self.sign_template._prepare_request(
            {self.customer_role: self.customer, self.company_role: self.company_contact}))
        template = self.sign_template
        template.invalidate_recordset()
        self.assertEqual((template.request_count, template.sent_request_count, template.signed_request_count,
                          template.share_request_count), (3, 2, 1, 0))
        self.assertEqual(self.env['sign.request'].search_count(template.action_open_signed_requests()['domain']), 1)
        self.assertEqual(self.env['sign.request'].search_count(template.action_open_sent_requests()['domain']), 2)

    def test_signer_summary_and_timeline(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids
        self.assertEqual([(signer['name'], signer['role'], signer['state']) for signer in sign_request.signer_summary],
                         [('Acme Buyer', 'Customer', 'to_sign'), ('Clara Company', 'Company', 'waiting')])
        customer.sudo()._opened()
        customer.sudo().action_send_again()
        self.env['sign.log']._log(sign_request, 'code_verified', signer=customer)
        customer.sudo()._sign('Acme Buyer', SIGNATURE)
        sign_request.invalidate_recordset()
        first, second = sign_request.signer_timeline
        self.assertEqual((first['state'], first['reminders']), ('signed', 1))
        self.assertTrue(first['date_invited'] and first['date_opened'] and first['date_verified']
                        and first['date_signed'])
        self.assertEqual(first['email'], 'buyer@example.com')
        self.assertEqual((second['state'], second['date_signed'], second['date_verified']), ('to_sign', False, False))
        self.assertTrue(second['date_invited'], 'asked once the customer signed')

    def test_deadline_past(self):
        sign_request = self.send_template()
        self.assertFalse(sign_request.is_deadline_past)
        sign_request.sudo().date_deadline = fields.Date.context_today(sign_request) - timedelta(days=1)
        self.assertTrue(sign_request.is_deadline_past)
        sign_request.sudo().state = 'expired'
        self.assertFalse(sign_request.is_deadline_past, 'only while it waits for signatures')

    # ------------------------------------------------------------------
    # The menus
    # ------------------------------------------------------------------

    def search_action(self, xmlid, user):
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        domain = safe_eval(action.get('domain') or '[]', {'uid': user.id})
        return self.env['sign.request'].with_user(user).search(domain)

    def test_menus_actions(self):
        partner = self.sender.partner_id
        # the sender signs first, then the customer: theirs to sign
        mine = self.upload_request([(10, 'Sender', partner), (20, 'Customer', self.customer)])
        # the customer signs first: waiting for the others
        others = self.upload_request([(10, 'Customer', self.customer), (20, 'Sender', partner)])
        done = self.upload_request([(10, 'Customer', self.customer)])
        self.sign(done, self.customer)
        draft = self.upload_request([(10, 'Customer', self.customer)], send=False)
        self.assertEqual(self.search_action('om_sign.sign_request_action_to_sign', self.sender), mine)
        waiting = self.search_action('om_sign.sign_request_action_waiting', self.sender)
        self.assertIn(others, waiting)
        self.assertNotIn(mine, waiting)
        self.assertEqual(self.search_action('om_sign.sign_request_action_completed', self.sender), done)
        self.assertEqual(self.search_action('om_sign.sign_request_action', self.sender), mine | others | done | draft,
                         'all the requests the user sent')
        self.assertEqual(self.search_action('om_sign.sign_request_action_to_sign', self.colleague),
                         self.env['sign.request'])

    def test_menus_visible(self):
        Menu = self.env['ir.ui.menu']
        to_sign = self.env.ref('om_sign.menu_sign_to_sign')
        waiting = self.env.ref('om_sign.menu_sign_waiting')
        templates = self.env.ref('om_sign.menu_sign_template')
        signer_menus = Menu.with_user(self.outsider)._visible_menu_ids()
        self.assertIn(to_sign.id, signer_menus, 'an employee who signs finds the documents to sign')
        self.assertNotIn(waiting.id, signer_menus)
        self.assertNotIn(templates.id, signer_menus)
        sender_menus = Menu.with_user(self.sender)._visible_menu_ids()
        self.assertTrue({to_sign.id, waiting.id, templates.id} <= set(sender_menus))

    def test_landing(self):
        Request = self.env['sign.request']
        everything = self.env.ref('om_sign.sign_request_action').id
        to_sign = self.env.ref('om_sign.sign_request_action_to_sign').id
        self.assertEqual(Request.with_user(self.manager).action_open_landing()['id'], everything)
        self.assertEqual(Request.with_user(self.sender).action_open_landing()['id'], to_sign)
        self.assertEqual(Request.with_user(self.outsider).action_open_landing()['id'], to_sign)
        root = self.env.ref('om_sign.menu_sign_root')
        self.assertEqual(root.action, self.env.ref('om_sign.sign_request_action_landing'))


@tagged('post_install', '-at_install')
class TestSignViewsTour(SignTemplateCommon, HttpCase):

    def test_kanbans_tour(self):
        template = self.sign_template
        template.name = 'Kanban Tour Contract'
        self.assertFalse(template.thumbnail)
        self.send_template()
        self.start_tour('/odoo/action-om_sign.sign_template_action', 'om_sign_kanbans', login='admin')
        self.assertTrue(template.thumbnail, 'drawn by the browser of the administrator, kept for the next time')
