from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPrintTemplate(TransactionCase):
    """ Printing on contacts: any model can be printed, without a module of its own. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_print_user', groups='base.group_user,base.group_partner_manager')
        cls.other_user = new_test_user(cls.env, 'om_print_other', groups='base.group_user')
        cls.partner = cls.env['res.partner'].create({'name': 'Acme Supplies'})
        cls.template = cls.env['print.template'].create({
            'name': 'Balance Confirmation',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'code': 'CONF/',
            'subject': 'Balance of {{ object.name }}',
            'body_html': '<p>We confirm the balance of <t t-out="object.name"/>.</p>',
            'signatory_name': 'Finance Manager',
        })

    def wizard(self, records, user=None):
        context = {'active_model': records._name, 'active_ids': records.ids,
                   'default_template_id': self.template.id}
        return Form(self.env['print.wizard'].with_user(user or self.user).with_context(**context))

    def issue(self, user=None):
        wizard = self.wizard(self.partner, user=user).save()
        action = wizard.action_issue()
        return self.env['print.issue'].search([('res_id', '=', self.partner.id)], limit=1), action

    def test_print_menu(self):
        action = self.template.ref_ir_act_window
        self.assertEqual((action.binding_model_id.model, action.binding_type), ('res.partner', 'report'))
        bindings = self.env['ir.actions.actions'].get_bindings('res.partner')
        self.assertIn(action.id, [binding['id'] for binding in bindings.get('report', [])])
        self.template.print_menu = False
        self.assertFalse(self.template.ref_ir_act_window)
        self.template.print_menu = True
        self.assertTrue(self.template.ref_ir_act_window)

    def test_wizard_preview(self):
        wizard = self.wizard(self.partner)
        self.assertIn('Acme Supplies', wizard.preview)
        self.assertEqual(wizard.addressee, 'To Whom It May Concern')

    def test_issue_numbers_and_freezes(self):
        issue, action = self.issue()
        self.assertEqual(issue.state, 'issued')
        self.assertTrue(issue.name.startswith('CONF/'))
        self.assertEqual(issue.subject, 'Balance of Acme Supplies')
        self.assertIn('Acme Supplies', issue.body_html)
        self.assertEqual(issue.issued_by_id, self.user)
        self.assertTrue(issue.attachment_id)
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn(str(issue.attachment_id.id), action['url'])

        self.partner.name = 'Acme Renamed'
        self.assertIn('Acme Supplies', issue.body_html, 'printed as it was')
        with self.assertRaises(UserError):
            issue.with_user(self.user).body_html = '<p>Changed</p>'
        with self.assertRaises(UserError):
            issue.unlink()

        second, _action = self.issue()
        self.assertNotEqual(second.name, issue.name, 'each print gets its own reference')

    def test_edit_before_issuing(self):
        wizard = self.wizard(self.partner).save()
        draft = self.env['print.issue'].browse(wizard.action_draft()['res_id'])
        self.assertEqual(draft.state, 'draft')
        draft.with_user(self.user).body_html = '<p>Adjusted for the bank.</p>'
        draft.with_user(self.user).action_issue()
        self.assertIn('Adjusted for the bank', draft.body_html)

    def test_several_records(self):
        partners = self.partner | self.env['res.partner'].create({'name': 'Beta Trading'})
        action = self.wizard(partners).save().action_issue()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(self.env['print.issue'].search_count([('res_id', 'in', partners.ids)]), 2)

    def test_cancel_and_access(self):
        issue, _action = self.issue()
        with self.assertRaises(UserError):
            issue.with_user(self.user).action_cancel()
        issue.action_cancel('Replaced')
        self.assertEqual((issue.state, issue.cancel_reason), ('cancelled', 'Replaced'))
        with self.assertRaises(AccessError):
            issue.with_user(self.other_user).read(['name'])

    def test_qr_only_when_asked(self):
        issue, _action = self.issue()
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_print_template.action_report_print_issue', issue.ids)[0].decode()
        self.assertNotIn('/report/barcode', html)
        self.template.show_qr = True
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_print_template.action_report_print_issue', issue.ids)[0].decode()
        self.assertIn('/report/barcode', html)
        self.assertIn('Finance Manager', html)

    def test_any_user_prints_a_trusted_template(self):
        """ The template editors write the expressions; the users printing need not be editors. """
        self.template.body_html = ('<p>On <t t-out="format_date(object.create_date)"/> '
                                   'for <t t-out="object.name.upper()"/>.</p>')
        printer = new_test_user(self.env, 'om_print_plain', groups='base.group_user,base.group_partner_manager')
        printer.group_ids -= self.env.ref('mail.group_mail_template_editor')
        self.assertFalse(printer.has_group('mail.group_mail_template_editor'))
        issue, _action = self.issue(user=printer)
        self.assertIn('ACME SUPPLIES', issue.body_html)
