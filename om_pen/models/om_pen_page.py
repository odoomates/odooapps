import re

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OmPenPage(models.Model):
    _name = 'om.pen.page'
    _description = "View Customization Page"
    _order = 'sequence, id'

    customize_id = fields.Many2one('om.pen.view', string="Customization",
                                   required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Technical Name", required=True)
    string = fields.Char(string="Title", required=True)
    published = fields.Boolean(
        string="Published",
        help="An unpublished page is not in the live view yet.")
    to_remove = fields.Boolean(
        string="Removed On Publish",
        help="The page stays in the live view until the next publish.")

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(customize_id, name)', "A page name must be unique per view."),
    ]

    @api.constrains('name')
    def _check_name(self):
        for page in self:
            if not re.fullmatch(r'x_[a-z0-9_]+', page.name or ''):
                raise ValidationError(_(
                    "A page name must start with x_ and hold only lowercase letters,"
                    " digits and underscores, not %s.") % page.name)

    @api.model
    def name_for(self, title):
        slug = re.sub(r'[^a-z0-9]+', '_', (title or '').lower()).strip('_') or 'page'
        return 'x_%s' % slug[:50]

    def _render_nodes(self, arch):
        """ Append the page to the view's notebook.

        A view with no notebook cannot take a page, and saying so up front beats
        writing an arch whose xpath silently fails to locate.
        """
        self.ensure_one()
        if not arch.xpath('//notebook'):
            raise ValidationError(_(
                "This view has no notebook, so the page %s cannot be added to it.") % self.string)
        spec = etree.Element('xpath', expr='//notebook', position='inside')
        etree.SubElement(spec, 'page', name=self.name, string=self.string)
        return [spec]
