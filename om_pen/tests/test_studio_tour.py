from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestStudioTour(HttpCase):
    """ The Studio lives in the browser: drive it. """

    def test_a_field_is_renamed_and_published(self):
        partner_form = self.env.ref('base.view_partner_form')
        action = self.env['ir.actions.act_window'].create({
            'name': "Studio Tour",
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.env.ref('base.partner_admin').id,
            'view_id': partner_form.id,
        })
        self.start_tour('/odoo/action-%s' % action.id, 'om_pen_studio_rename_tour', login='admin', timeout=120)
        customization = self.env['om.pen.view'].search([('view_id', '=', partner_form.id)])
        self.assertTrue(customization.published_ops, "the change must be published")
        self.assertIn("Role On Site", customization.custom_view_id.arch)

    def test_an_app_is_built(self):
        self.start_tour('/odoo/action-base.action_partner_form', 'om_pen_studio_app_tour', login='admin', timeout=180)
        model = self.env['ir.model'].search([('name', '=', "Tour Vehicle")])
        self.assertTrue(model, "the app builder must have made the model")
        self.assertTrue(self.env['ir.ui.menu'].search([('name', '=', "Tour Fleet")]))
