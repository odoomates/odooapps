import base64
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
@freeze_time('2026-06-01')
class TestDocument(TransactionCase):
    """ Documents kept on contacts: a model without the mixin, so the users of the type are reminded. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.responsible = new_test_user(cls.env, 'om_document_responsible', groups='base.group_user')
        cls.partner = cls.env['res.partner'].create({'name': 'Vendor', 'email': 'vendor@example.com'})
        cls.doc_type = cls.env['document.type'].create({
            'name': 'Insurance Certificate', 'code': 'INSURANCE',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'reminder_days': '30,7,0', 'user_ids': [Command.link(cls.responsible.id)],
        })

    def new_document(self, date_expiry, **values):
        return self.env['document.document'].create({
            'res_model': 'res.partner', 'res_id': self.partner.id, 'type_id': self.doc_type.id,
            'number': 'INS-1', 'date_expiry': date_expiry, **values})

    def todos(self, document):
        return document.activity_ids.filtered(lambda activity: activity.user_id == self.responsible)

    def test_name_and_state(self):
        document = self.new_document(date(2026, 9, 1))
        self.assertEqual(document.name, 'Insurance Certificate INS-1')
        self.assertEqual(document.res_name, 'Vendor')
        self.assertEqual((document.state, document.days_left), ('valid', 92))
        self.assertEqual(self.new_document(date(2026, 6, 20)).state, 'expiring')
        self.assertEqual(self.new_document(date(2026, 5, 31)).state, 'expired')
        self.assertEqual(self.new_document(False).state, 'none')

    def test_search_state(self):
        valid = self.new_document(date(2026, 9, 1))
        expiring = self.new_document(date(2026, 6, 20))
        expired = self.new_document(date(2026, 5, 31))
        none = self.new_document(False)
        Document = self.env['document.document']
        mine = [('res_id', '=', self.partner.id)]
        self.assertEqual(Document.search(mine + [('state', 'in', ['expiring'])]), expiring)
        self.assertEqual(Document.search(mine + [('state', 'in', ['expired'])]), expired)
        self.assertEqual(Document.search(mine + [('state', '=', 'valid')]), valid)
        self.assertEqual(Document.search(mine + [('state', 'in', ['none'])]), none)
        self.assertEqual(Document.search(mine + [('state', 'not in', ['expiring', 'expired'])]), valid | none)

    def test_checks(self):
        with self.assertRaises(ValidationError):
            self.new_document(date(2026, 1, 1), date_issue=date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            self.doc_type.reminder_days = '30,soon'
        other_type = self.env['document.type'].create({
            'name': 'Badge', 'model_id': self.env['ir.model']._get_id('res.users')})
        with self.assertRaises(ValidationError):
            self.new_document(False, type_id=other_type.id)

    def test_reminders_fire_once_per_stage(self):
        document = self.new_document(date(2026, 6, 25))
        Document = self.env['document.document']
        Document._cron_send_reminders()
        self.assertEqual(len(self.todos(document)), 1, '24 days left: the 30 days reminder')
        self.assertEqual(document.last_reminder, 30)
        Document._cron_send_reminders()
        self.assertEqual(len(self.todos(document)), 1, 'not twice')
        with freeze_time('2026-06-19'):
            Document._cron_send_reminders()
            self.assertEqual(len(self.todos(document)), 2, '6 days left: the 7 days reminder')
        with freeze_time('2026-06-26'):
            Document._cron_send_reminders()
            Document._cron_send_reminders()
            self.assertEqual(len(self.todos(document)), 3, 'expired: the last reminder, once')
        document.date_expiry = date(2027, 6, 1)
        self.assertEqual(document.last_reminder, -1, 'a new expiry date is reminded of again')
        document.date_expiry = date(2027, 6, 1)
        self.assertEqual(document.last_reminder, -1)

    def test_holder_notified(self):
        self.doc_type.notify_holder = True
        # contacts have no mixin: give their model the hook for the test
        patcher = patch.object(type(self.partner), '_document_holder_partner', lambda self: self, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        document = self.new_document(date(2026, 6, 10))
        self.env['document.document']._cron_send_reminders()
        message = document.message_ids.filtered(lambda m: self.partner in m.partner_ids)
        self.assertTrue(message, 'the holder is emailed')

    def test_renew(self):
        document = self.new_document(date(2026, 6, 20))
        context = document.action_renew()['context']
        renewal = self.env['document.document'].with_context(**context).create({
            'number': 'INS-2', 'date_expiry': date(2027, 6, 20)})
        self.assertEqual((renewal.res_model, renewal.res_id, renewal.type_id),
                         ('res.partner', self.partner.id, self.doc_type))
        self.assertEqual(renewal.previous_id, document)
        self.assertFalse(document.active, 'the renewed document is archived')
        self.assertEqual(document.next_id, renewal)

    def test_board(self):
        valid = self.new_document(date(2026, 9, 1))
        other_type = self.env['document.type'].create({
            'name': 'Tax Certificate', 'model_id': self.env['ir.model']._get_id('res.partner')})
        Document = self.env['document.document']
        data = Document.board_data('res.partner', self.partner.id)
        self.assertEqual([doc['id'] for doc in data['documents']], [valid.id])
        self.assertIn(other_type.id, [missing['id'] for missing in data['missing']])
        self.assertNotIn(self.doc_type.id, [missing['id'] for missing in data['missing']])

        file = {'name': 'tax.pdf', 'mimetype': 'application/pdf', 'data': base64.b64encode(b'%PDF-1.4').decode()}
        new_id = Document.board_upload('res.partner', self.partner.id, other_type.id, False, [file])
        created = Document.browse(new_id)
        self.assertEqual((created.type_id, created.attachment_ids.name), (other_type, 'tax.pdf'))
        self.assertEqual(created.attachment_ids.res_model, 'document.document')
        Document.board_upload('res.partner', self.partner.id, False, valid.id, [file, dict(file, name='b.pdf')])
        self.assertEqual(len(valid.attachment_ids), 2)
