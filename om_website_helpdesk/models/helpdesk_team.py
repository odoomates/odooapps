from odoo import api, fields, models


class OmHelpdeskTeam(models.Model):
    _inherit = 'om.helpdesk.team'

    website_form = fields.Boolean(
        string='Website Form',
        help="Publish a ticket form for this team on the website, on the Help page.")
    website_id = fields.Many2one(
        'website', string='Website', ondelete='set null',
        domain="[('company_id', 'in', [company_id, False])]",
        help="Website showing the form. Leave empty to show it on every website of the company.")
    website_url = fields.Char(string='Form URL', compute='_compute_website_url')

    @api.depends('website_form', 'name')
    def _compute_website_url(self):
        IrHttp = self.env['ir.http']
        for team in self:
            team.website_url = f'/helpdesk/{IrHttp._slug(team)}' if team.website_form and team.id else False

    @api.model
    def _get_website_teams(self, website):
        """ Teams that publish their form on the given website. """
        return self.sudo().search([
            ('website_form', '=', True),
            ('company_id', '=', website.company_id.id),
            ('website_id', 'in', [website.id, False]),
        ])

    def action_open_website_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.website_url,
            'target': 'new',
        }
