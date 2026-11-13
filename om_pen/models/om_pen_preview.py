from lxml import etree

from odoo import api, models
from odoo.fields import Domain

DRAFT_OPTION = 'om_pen_draft'


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    @api.model
    def _get_inheriting_views_domain(self):
        """ Leave the generated views out while a draft is previewed.

        The draft is rendered from every rule, published or not, so combining it with
        the published generated view as well would apply the published rules twice.
        """
        domain = super()._get_inheriting_views_domain()
        if self.env.context.get(DRAFT_OPTION):
            generated = self.env['om.pen.view'].sudo().search(
                [('custom_view_id', '!=', False)]).custom_view_id
            if generated:
                domain &= Domain('id', 'not in', generated.ids)
        return domain


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _om_pen_previews_draft(self, options):
        """ Whether this request shows the customizer's draft instead of the live view.

        The web client asks for it while customize mode is on. Only someone who may
        customize gets it: everybody else always sees what is published.
        """
        return bool(options.get(DRAFT_OPTION)) and self.env.user.has_group('om_pen.group_customizer')

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        if self._om_pen_previews_draft(options):
            # a separate cache entry, so a draft never reaches a published view's users
            key += ((DRAFT_OPTION, True),)
        return key

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """ The view with the unpublished changes applied, while customizing.

        Without this, a field dropped onto a form would not show until it is
        published, which makes placing anything a guess.
        """
        if not self._om_pen_previews_draft(options):
            return super()._get_view(view_id, view_type, **options)
        preview = self.with_context(**{DRAFT_OPTION: True})
        arch, view = super(Base, preview)._get_view(view_id, view_type, **options)
        customization = preview.env['om.pen.view'].sudo().search(
            [('view_id', '=', view.id)], limit=1)
        if customization and customization.active:
            specs = etree.fromstring(customization._render_arch(draft=True))
            if len(specs):
                arch = view.with_context(**{DRAFT_OPTION: True}).apply_inheritance_specs(arch, specs)
        return arch, view
