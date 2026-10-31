import io
from datetime import timedelta

from reportlab.pdfgen import canvas

from odoo import fields
from odoo.tests import new_test_user
from odoo.tools.binary import BinaryBytes
from odoo.tools.pdf import NameObject, NumberObject, PdfFileReader, PdfFileWriter, RectangleObject

# a 1 x 1 PNG, as the signature pad sends it
SIGNATURE = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='


def blank_pdf():
    writer = PdfFileWriter()
    writer.add_blank_page(width=200, height=200)
    with io.BytesIO() as stream:
        writer.write(stream)
        return stream.getvalue()


def make_pdf(pages=2, size=(595, 842), rotate=None, mediabox=None):
    """ :return: a PDF of `pages` pages of `size` points, each saying "Original page N"; `rotate` and `mediabox`
                 give the rotation and the media box of a page by its number """
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=size)
    for number in range(1, pages + 1):
        pdf.drawString(50, size[1] - 50, 'Original page %s' % number)
        pdf.showPage()
    pdf.save()
    if not rotate and not mediabox:
        return stream.getvalue()
    writer = PdfFileWriter()
    writer.append(PdfFileReader(io.BytesIO(stream.getvalue())))
    for number, angle in (rotate or {}).items():
        writer.pages[number - 1][NameObject('/Rotate')] = NumberObject(angle)
    for number, box in (mediabox or {}).items():
        writer.pages[number - 1].mediabox = RectangleObject(box)
    with io.BytesIO() as output:
        writer.write(output)
        return output.getvalue()


def text_positions(page):
    """ :return: the texts of a pypdf `page` with the point of the PDF where each starts, as (text, x, y) """
    found = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            found.append((text.strip(), x, y))

    page.extract_text(visitor_text=visit)
    return found


class SignCommon:
    """ Contacts signing the documents: a customer, then a witness. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sender = new_test_user(cls.env, 'om_sign_sender', groups='base.group_user,om_sign.group_sign_user',
                                   email='sender@example.com')
        cls.outsider = new_test_user(cls.env, 'om_sign_outsider', groups='base.group_user',
                                     email='outsider@example.com')
        cls.customer = cls.env['res.partner'].create({'name': 'Acme Buyer', 'email': 'buyer@example.com'})
        cls.witness = cls.env['res.partner'].create({'name': 'Wanda Witness', 'email': 'witness@example.com'})

    def request_for_customer(self, send=True, **values):
        """ :return: an uploaded PDF about the customer, signed by the customer, then the witness, within 14 days """
        sign_request = self.upload_request([(10, 'Customer', self.customer), (20, 'Witness', self.witness)],
                                           send=False)
        sign_request.write({'res_model': 'res.partner', 'res_id': self.customer.id,
                            'date_deadline': fields.Date.today() + timedelta(days=14), **values})
        if send:
            sign_request.action_send()
        return sign_request

    def upload_request(self, signers, send=True):
        sign_request = self.env['sign.request'].with_user(self.sender).create({
            'name': 'Uploaded Contract',
            'document_file': BinaryBytes(blank_pdf()),
            'document_filename': 'contract.pdf',
            'signer_ids': [(0, 0, {'sequence': sequence, 'role_name': role, 'partner_id': partner.id})
                           for sequence, role, partner in signers],
        })
        if send:
            sign_request.action_send()
        return sign_request

    @staticmethod
    def signer_of(sign_request, partner):
        return sign_request.signer_ids.filtered(lambda signer: signer.partner_id == partner)

    def sign(self, sign_request, partner):
        self.signer_of(sign_request, partner).sudo()._sign(partner.name, SIGNATURE)
