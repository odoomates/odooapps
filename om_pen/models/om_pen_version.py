import difflib

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmPenVersion(models.Model):
    _name = 'om.pen.version'
    _description = "Published Version Of A View Customization"
    _order = 'id desc'

    customize_id = fields.Many2one('om.pen.view', string="Customization", required=True,
                                   ondelete='cascade', index=True)
    ops = fields.Json(string="Changes", default=list)
    arch = fields.Text(string="Generated View")
    change_count = fields.Integer(string="Number of Changes", compute='_compute_change_count')

    @api.depends('ops')
    def _compute_change_count(self):
        for version in self:
            version.change_count = len(version.ops or [])

    @api.depends('create_date', 'create_uid')
    def _compute_display_name(self):
        for version in self:
            version.display_name = "%s, %s" % (
                fields.Datetime.to_string(version.create_date) if version.create_date else '',
                version.create_uid.name or '')

    def _previous(self):
        self.ensure_one()
        return self.search([('customize_id', '=', self.customize_id.id), ('id', '<', self.id)],
                           order='id desc', limit=1)

    def _diff(self):
        """ The generated view of this version against the one published before it. """
        self.ensure_one()
        before = (self._previous().arch or '').splitlines()
        after = (self.arch or '').splitlines()
        return list(difflib.unified_diff(before, after, lineterm='', n=2))[2:]

    def _restore(self):
        """ Make this version the draft again; publishing it puts it back live. """
        self.ensure_one()
        customization = self.customize_id
        if customization.draft_ops == self.ops:
            raise UserError(_("The draft is already this version."))
        customization._set_draft(list(self.ops or []))
