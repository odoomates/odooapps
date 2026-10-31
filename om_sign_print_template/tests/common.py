from odoo.addons.om_sign.tests.common import SignCommon


class SignPrintCommon(SignCommon):
    """ A template printed for contacts, signed by the contact and then a witness. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env['print.template'].create({
            'name': 'Agreement',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'subject': 'Agreement with {{ object.name }}',
            'body_html': '<p>We agree with <t t-out="object.name"/>.</p>',
            'sign_reminder_days': 3,
            'sign_validity_days': 14,
            'sign_role_ids': [
                (0, 0, {'sequence': 10, 'name': 'Customer', 'signer_type': 'field'}),
                (0, 0, {'sequence': 20, 'name': 'Witness', 'signer_type': 'partner', 'partner_id': cls.witness.id}),
            ],
        })

    def issue(self, partner=None):
        Issue = self.env['print.issue'].with_user(self.sender)
        issue = Issue._create_from_template(self.template, (partner or self.customer).ids)
        issue.action_issue()
        return issue

    def request_for_issue(self, send=True):
        sign_request = self.env['sign.request'].with_user(self.sender)._create_for_issue(self.issue())
        if send:
            sign_request.action_send()
        return sign_request
