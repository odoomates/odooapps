import base64
import hashlib
import io
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.tools.binary import BinaryBytes
from odoo.tools.pdf import PdfFileReader

from ..models.stamp import stamp_pdf
from .common import SIGNATURE, SignCommon, make_pdf, text_positions

A4 = (595, 842)


class SignTemplateCommon(SignCommon):
    """ A two-page contract signed by the customer, then by a given contact of the company. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_contact = cls.env['res.partner'].create({
            'name': 'Clara Company', 'email': 'clara@example.com'})
        cls.customer.parent_id = cls.env['res.partner'].create({'name': 'Acme Corp'})
        cls.pdf = make_pdf(2, A4)
        cls.sign_template = cls.env['sign.template'].with_user(cls.sender).create({
            'name': 'Service Contract',
            'document_file': BinaryBytes(cls.pdf),
            'document_filename': 'service.pdf',
            'role_ids': [
                Command.create({'name': 'Customer', 'sequence': 1, 'color': 1}),
                Command.create({'name': 'Company', 'sequence': 2, 'color': 4, 'signer_type': 'partner',
                                'partner_id': cls.company_contact.id}),
            ],
        })
        cls.customer_role, cls.company_role = cls.sign_template.role_ids
        Field = cls.env['sign.template.field'].with_user(cls.sender)
        field = {'template_id': cls.sign_template.id, 'role_id': cls.customer_role.id, 'width': 0.3, 'height': 0.03}
        cls.f_signature = Field.create({**field, 'type': 'signature', 'page': 1, 'pos_x': 0.1, 'pos_y': 0.6,
                                        'height': 0.06, 'label': 'Customer signature'})
        cls.f_name = Field.create({**field, 'type': 'name', 'page': 1, 'pos_x': 0.1, 'pos_y': 0.8})
        cls.f_company = Field.create({**field, 'type': 'company', 'page': 1, 'pos_x': 0.5, 'pos_y': 0.8})
        cls.f_date = Field.create({**field, 'type': 'date', 'page': 2, 'pos_x': 0.1, 'pos_y': 0.2})
        cls.f_text = Field.create({**field, 'type': 'text', 'page': 2, 'pos_x': 0.1, 'pos_y': 0.3,
                                   'required': False, 'label': 'Job title'})
        cls.f_check = Field.create({**field, 'type': 'checkbox', 'page': 2, 'pos_x': 0.1, 'pos_y': 0.4,
                                    'width': 0.03, 'height': 0.02, 'required': False})
        field['role_id'] = cls.company_role.id
        cls.f_company_signature = Field.create({**field, 'type': 'signature', 'page': 2, 'pos_x': 0.6,
                                                'pos_y': 0.7, 'height': 0.06})
        cls.f_company_email = Field.create({**field, 'type': 'email', 'page': 2, 'pos_x': 0.6, 'pos_y': 0.8})

    def send_template(self, customer=None, template=None):
        template = template or self.sign_template
        wizard = Form(self.env['sign.send'].with_user(self.sender).with_context(default_template_id=template.id))
        for index in range(len(wizard.line_ids)):
            with wizard.line_ids.edit(index) as line:
                if not line.partner_id:
                    line.partner_id = customer or self.customer
        action = wizard.save().action_send()
        return self.env['sign.request'].browse(action['res_id'])

    @staticmethod
    def value_of(signer, field):
        return signer.sudo().value_ids.filtered(lambda value: value.field_id == field)


@tagged('post_install', '-at_install')
class TestSignTemplate(SignTemplateCommon, TransactionCase):

    # ------------------------------------------------------------------
    # Templates and the editor
    # ------------------------------------------------------------------

    def test_upload_creates_template(self):
        upload = self.env['sign.template.upload'].with_user(self.sender).create({
            'document_file': BinaryBytes(make_pdf(3)), 'document_filename': 'Lease Agreement.pdf'})
        action = upload.action_upload()
        self.assertEqual(action['tag'], 'om_sign_template_editor')
        template = self.env['sign.template'].browse(action['params']['template_id'])
        self.assertEqual(template.name, 'Lease Agreement')
        self.assertEqual(template.page_count, 3)
        self.assertEqual(template.role_ids.mapped('name'), ['Customer'], 'a first role to place fields for')
        self.assertEqual(template.company_id, self.env.company)

        not_pdf = self.env['sign.template.upload'].with_user(self.sender).create({
            'document_file': BinaryBytes(b'hello'), 'document_filename': 'notes.txt'})
        with self.assertRaises(UserError):
            not_pdf.action_upload()
        with self.assertRaises(ValidationError), mute_logger('pypdf._reader'):
            template.document_file = BinaryBytes(b'%PDF-1.4 broken')

    def test_editor_load_and_save(self):
        data = self.env['sign.template'].with_user(self.sender).editor_load(self.sign_template.id)
        self.assertEqual(data['template']['page_count'], 2)
        self.assertEqual([role['name'] for role in data['roles']], ['Customer', 'Company'])
        self.assertEqual(len(data['fields']), 8)
        self.assertTrue(data['can_edit'])

        # the customer renamed, the company replaced by a witness, a field moved and one added for the witness
        customer = dict(data['roles'][0], name='Buyer')
        witness = {'id': 'new_1', 'name': 'Witness', 'sequence': 2, 'color': 10, 'signer_type': 'requester'}
        moved = dict(next(field for field in data['fields'] if field['id'] == self.f_signature.id),
                     page=2, pos_x=0.5, pos_y=0.5)
        added = {'id': 'new_2', 'role_id': 'new_1', 'type': 'initials', 'page': 1, 'pos_x': 0.8, 'pos_y': 0.9,
                 'width': 0.1, 'height': 0.05, 'required': True, 'label': ''}
        result = self.env['sign.template'].with_user(self.sender).editor_save(
            self.sign_template.id, {'roles': [customer, witness], 'fields': [moved, added]})
        template = self.sign_template
        self.assertEqual(template.role_ids.mapped('name'), ['Buyer', 'Witness'])
        self.assertEqual(template.role_ids[0], self.customer_role, 'the role kept its record')
        self.assertEqual(template.role_ids[1].signer_type, 'requester')
        self.assertEqual(len(template.field_ids), 2, 'the fields not in the editor are deleted')
        self.assertEqual((self.f_signature.page, self.f_signature.pos_x), (2, 0.5))
        initials = template.field_ids - self.f_signature
        self.assertEqual((initials.type, initials.role_id.name), ('initials', 'Witness'))
        self.assertEqual(len(result['fields']), 2)

        added.update(id=initials.id, role_id=initials.role_id.id)
        out_of_page = dict(added, pos_x=0.95)
        with self.assertRaises(ValidationError):
            self.env['sign.template'].with_user(self.sender).editor_save(
                template.id, {'roles': result['roles'], 'fields': [out_of_page]})
        no_page = dict(added, page=3)
        with self.assertRaises(ValidationError):
            self.env['sign.template'].with_user(self.sender).editor_save(
                template.id, {'roles': result['roles'], 'fields': [no_page]})
        with self.assertRaises(UserError):
            self.env['sign.template'].with_user(self.sender).editor_save(
                template.id, {'roles': result['roles'], 'fields': [dict(added, type='stamp')]})

    def test_templates_of_others(self):
        other = new_test_user(self.env, 'om_sign_other_sender', groups='base.group_user,om_sign.group_sign_user')
        self.assertEqual(self.sign_template.with_user(other).name, 'Service Contract', 'others send it too')
        data = self.env['sign.template'].with_user(other).editor_load(self.sign_template.id)
        self.assertFalse(data['can_edit'])
        with self.assertRaises(AccessError):
            self.env['sign.template'].with_user(other).editor_save(self.sign_template.id, data)
        with self.assertRaises(AccessError):
            self.sign_template.with_user(self.outsider).read(['name'])

    def test_copy(self):
        copy = self.sign_template.copy()
        self.assertEqual(copy.name, 'Service Contract (copy)')
        self.assertEqual(copy.role_ids.mapped('name'), ['Customer', 'Company'])
        self.assertEqual(len(copy.field_ids), 8)
        self.assertEqual(copy.field_ids.role_id, copy.role_ids, 'the fields belong to the roles of the copy')

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def test_send(self):
        self.sign_template.write({'validity_days': 10, 'reminder_days': 2, 'message': 'Please sign.'})
        wizard = self.env['sign.send'].with_user(self.sender).create({'template_id': self.sign_template.id})
        self.assertEqual(wizard.name, 'Service Contract')
        self.assertEqual(wizard.date_deadline, fields.Date.today() + timedelta(days=10))
        self.assertEqual(wizard.message, 'Please sign.')
        self.assertEqual(wizard.line_ids.role_id, self.customer_role | self.company_role)
        self.assertFalse(wizard.line_ids[0].partner_id, 'the customer is chosen when sending')
        self.assertEqual(wizard.line_ids[1].partner_id, self.company_contact, 'the company signs with its contact')
        with self.assertRaisesRegex(UserError, 'Customer'):
            wizard.action_send()
        self.company_role.signer_type = 'requester'
        wizard = self.env['sign.send'].with_user(self.sender).create({'template_id': self.sign_template.id})
        self.assertEqual(wizard.line_ids[1].partner_id, self.sender.partner_id, 'the person sending signs')
        self.company_role.write({'signer_type': 'partner', 'partner_id': self.company_contact.id})

        sign_request = self.send_template()
        self.assertEqual(sign_request.sign_template_id, self.sign_template)
        self.assertEqual(sign_request.state, 'sent')
        self.assertEqual(sign_request.document_hash, hashlib.sha256(self.pdf).hexdigest())
        self.assertEqual(sign_request.document_filename, 'service.pdf')
        self.assertEqual((sign_request.reminder_days, sign_request.message), (2, 'Please sign.'))
        customer, company = sign_request.signer_ids
        self.assertEqual((customer.partner_id, company.partner_id), (self.customer, self.company_contact))
        self.assertEqual((customer.template_role_id, company.template_role_id),
                         (self.customer_role, self.company_role))
        self.assertEqual((customer.state, company.state), ('to_sign', 'waiting'), 'they sign in order')
        self.assertEqual(len(customer.sudo().value_ids), 6)
        self.assertEqual(len(company.sudo().value_ids), 2)
        self.assertEqual(self.sign_template.request_count, 1)

        # the request keeps the fields as they were sent
        self.f_signature.pos_x = 0.5
        self.assertEqual(self.value_of(customer, self.f_signature).pos_x, 0.1)

    def test_send_needs_every_role(self):
        sign_request = self.env['sign.request'].with_user(self.sender).create({
            'name': 'Partial', 'sign_template_id': self.sign_template.id,
            'signer_ids': [Command.create({'partner_id': self.customer.id, 'template_role_id': self.customer_role.id})],
        })
        with self.assertRaisesRegex(UserError, 'Company'):
            sign_request.action_send()
        self.assertEqual(sign_request.state, 'draft')
        self.assertFalse(sign_request.sudo().value_ids)

    def test_template_in_use(self):
        self.send_template()
        with self.assertRaises(UserError):
            self.sign_template.unlink()
        self.sign_template.action_archive()
        self.assertFalse(self.sign_template.active)

    # ------------------------------------------------------------------
    # Filling the fields
    # ------------------------------------------------------------------

    def test_sign_fields_validation(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids.sudo()
        signature = self.value_of(customer, self.f_signature).id
        name = self.value_of(customer, self.f_name).id
        check = self.value_of(customer, self.f_check).id
        text = self.value_of(customer, self.f_text).id
        date = self.value_of(customer, self.f_date).id
        valid = {signature: SIGNATURE, name: 'Acme Buyer'}

        with self.assertRaisesRegex(UserError, 'own fields'):
            customer._sign_fields({**valid, self.value_of(company, self.f_company_signature).id: SIGNATURE})
        with self.assertRaisesRegex(UserError, 'own fields'):
            customer._sign_fields({**valid, 'not an id': 'x'})
        with self.assertRaisesRegex(UserError, 'Customer signature'):
            customer._sign_fields({name: 'Acme Buyer'})
        with self.assertRaisesRegex(UserError, 'Name'):
            customer._sign_fields({signature: SIGNATURE, name: '   '})
        with self.assertRaises(UserError):
            customer._sign_fields({**valid, check: 'yes'})
        with self.assertRaises(UserError):
            customer._sign_fields({**valid, date: '31/10/2026'})
        with self.assertRaises(UserError):
            customer._sign_fields({**valid, date: '2026-02-30'})
        with self.assertRaises(UserError):
            customer._sign_fields({**valid, text: 42})
        with self.assertRaises(UserError):
            customer._sign_fields({signature: 'not an image', name: 'Acme Buyer'})
        with self.assertRaises(UserError):
            customer._sign_fields({signature: base64.b64encode(b'GIF89a' + b'0' * 20).decode(), name: 'Acme'})
        with self.assertRaisesRegex(UserError, 'too long'):
            customer._sign_fields({**valid, text: 'x' * 1001})
        with self.assertRaisesRegex(UserError, 'too large'):
            customer._sign_fields({**valid, signature: 'A' * (3 * 1024 * 1024)})
        with self.assertRaises(UserError):
            company._sign_fields({self.value_of(company, self.f_company_signature).id: SIGNATURE})
        self.value_of(customer, self.f_check).required = True
        with self.assertRaisesRegex(UserError, 'Tick'):
            customer._sign_fields({**valid, check: False})
        self.assertEqual(customer.state, 'to_sign', 'nothing was signed')
        self.assertFalse(customer.sudo().value_ids.filtered('is_filled'), 'nothing was written')

        customer._sign_fields({**valid, check: True, text: '  Buyer  ', date: '2026-10-30'})
        self.assertEqual(customer.state, 'signed')
        self.assertEqual(customer.signed_name, 'Acme Buyer', 'signed as the name filled in')
        self.assertTrue(customer.signature, 'the drawn signature goes on the certificate')
        values = {value.field_id: value for value in customer.value_ids}
        self.assertEqual(values[self.f_text].value_text, 'Buyer')
        self.assertEqual(values[self.f_date].value_text, '2026-10-30')
        self.assertEqual(values[self.f_company].value_text, 'Acme Corp', 'filled for the signer')
        self.assertTrue(values[self.f_check].value_bool)
        self.assertEqual(company.state, 'to_sign')
        with self.assertRaises(UserError):
            customer._sign_fields(valid)

    def test_sign_fields_needs_the_code(self):
        self.sign_template.email_code = True
        customer = self.send_template().signer_ids[0].sudo()
        with self.assertRaisesRegex(UserError, 'code'):
            customer._sign_fields({self.value_of(customer, self.f_signature).id: SIGNATURE})

    def test_simple_signing_page_fills_the_fields(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids.sudo()
        self.assertFalse(customer._fields_to_fill())
        customer._sign('Acme Buyer', SIGNATURE)
        values = {value.field_id: value for value in customer.value_ids}
        self.assertTrue(values[self.f_signature].value_image)
        self.assertEqual(values[self.f_name].value_text, 'Acme Buyer')
        self.assertEqual(values[self.f_date].value_text, fields.Date.to_string(fields.Date.today()))
        self.assertFalse(values[self.f_text].value_text, 'an optional text is left empty')
        self.assertFalse(values[self.f_check].value_bool)
        company._sign('Clara', SIGNATURE)
        self.assertEqual(self.value_of(company, self.f_company_email).value_text, 'clara@example.com')
        self.assertEqual(sign_request.state, 'signed')

    def test_simple_signing_page_cannot_fill_texts(self):
        self.f_text.required = True
        customer = self.send_template().signer_ids[0].sudo()
        self.assertEqual(customer._fields_to_fill().field_id, self.f_text)
        with self.assertRaisesRegex(UserError, 'Job title'):
            customer._sign('Acme Buyer', SIGNATURE)
        self.assertEqual(customer.state, 'to_sign')

    def test_values_access(self):
        sign_request = self.send_template(customer=self.outsider.partner_id)
        mine = sign_request.signer_ids[0].sudo().value_ids
        Value = self.env['sign.request.value'].with_user(self.outsider)
        self.assertEqual(Value.search([('request_id', '=', sign_request.id)]), mine,
                         'a signer reads their own fields only')
        with self.assertRaises(AccessError):
            sign_request.signer_ids[1].sudo().value_ids.with_user(self.outsider).read(['value_text'])
        with self.assertRaises(UserError):
            mine.with_user(self.outsider).write({'value_text': 'forged'})
        with self.assertRaises(UserError):
            mine.with_user(self.sender).write({'value_text': 'forged'})
        self.assertEqual(len(self.env['sign.request.value'].with_user(self.sender).search(
            [('request_id', '=', sign_request.id)])), 8, 'the sender reads them all')

    # ------------------------------------------------------------------
    # The signed PDF
    # ------------------------------------------------------------------

    def test_stamped_pdf(self):
        sign_request = self.send_template()
        customer, company = sign_request.signer_ids.sudo()
        customer._sign_fields({
            self.value_of(customer, self.f_signature).id: SIGNATURE,
            self.value_of(customer, self.f_name).id: 'Acme Buyer',
            self.value_of(customer, self.f_text).id: 'Purchasing Manager',
            self.value_of(customer, self.f_check).id: True,
            self.value_of(customer, self.f_date).id: '2026-10-30',
        })
        company._sign('Clara', SIGNATURE)
        self.assertEqual(sign_request.state, 'signed')
        signed = sign_request.signed_attachment_id.raw.content
        self.assertEqual(sign_request.signed_hash, hashlib.sha256(signed).hexdigest())
        self.assertTrue(signed.startswith(b'%PDF'), 'the stamped document comes first')
        self.assertIn(b'Signature Certificate', signed)

        stamped = PdfFileReader(io.BytesIO(sign_request._stamp_document()))
        self.assertEqual(len(stamped.pages), 2, 'the pages of the PDF are kept')
        first = text_positions(stamped.pages[0])
        texts = [text for text, _x, _y in first]
        self.assertIn('Original page 1', texts, 'its content is kept')
        _text, x, y = next(position for position in first if position[0] == 'Acme Buyer')
        # the name field: 10% from the left, from 80% to 83% from the top of the page
        self.assertAlmostEqual(x, 0.1 * A4[0], delta=2)
        self.assertTrue(A4[1] * (1 - 0.83) <= y <= A4[1] * (1 - 0.8), y)
        self.assertIn('Acme Corp', texts)
        second = [text for text, _x, _y in text_positions(stamped.pages[1])]
        self.assertIn('Purchasing Manager', second)
        self.assertIn('clara@example.com', second)
        self.assertIn('10/30/2026', second, 'the date in the language of the signer')
        self.assertIn('Original page 2', second)

    def test_stamp_rotated_and_offset_pages(self):
        pdf = make_pdf(2, A4, rotate={2: 90}, mediabox={1: [-100, -50, 495, 792]})
        items = [{'page': page, 'pos_x': 0.1, 'pos_y': 0.1, 'width': 0.5, 'height': 0.05, 'kind': 'text',
                  'value': 'Stamp %s' % page} for page in (1, 2)]
        stamped = PdfFileReader(io.BytesIO(stamp_pdf(pdf, items)))
        # page 1: 595 x 842 from (-100, -50); the text starts 10% from its left, near its top
        _text, x, y = next(found for found in text_positions(stamped.pages[0]) if found[0] == 'Stamp 1')
        self.assertAlmostEqual(x, -100 + 59.5, delta=2)
        self.assertTrue(792 - 0.15 * 842 <= y <= 792 - 0.1 * 842, y)
        # page 2, turned a quarter clockwise: shown 842 x 595; 10% from the left of the page shown is 10% from
        # the bottom of the page in the PDF, 10% from the top shown is 10% from its left
        _text, x, y = next(found for found in text_positions(stamped.pages[1]) if found[0] == 'Stamp 2')
        self.assertAlmostEqual(y, 0.1 * 842, delta=2)
        self.assertTrue(0.1 * 595 <= x <= 0.15 * 595, x)

    def test_requests_without_template_unchanged(self):
        sign_request = self.upload_request([(10, 'Buyer', self.customer)])
        self.assertFalse(sign_request.sudo().value_ids)
        self.sign(sign_request, self.customer)
        signed = sign_request.signed_attachment_id.raw.content
        self.assertTrue(signed.startswith(sign_request.document_file.content), 'then the signature page')
