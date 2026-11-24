import logging

from lxml import etree

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

DRAFT_OPTION = 'om_pen_draft'
# context key: apply every change or fail, instead of skipping the ones that no
# longer fit (used when publishing, so a broken change is refused up front)
STRICT_KEY = 'om_pen_strict'


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

    @api.model
    def apply_inheritance_specs(self, source, specs_tree, pre_locate=None):
        """ Skip, rather than fail on, a generated change that no longer fits.

        A module update can move or remove what a customization points at. Failing
        would break the whole view and the update with it; skipping leaves the rest of
        the customization working, and the health check lists what was skipped.
        """
        from .om_pen_view import GENERATED_KEY
        if len(self) != 1 or not (self.key or '').startswith(GENERATED_KEY) \
                or self.env.context.get(STRICT_KEY):
            return super().apply_inheritance_specs(source, specs_tree, pre_locate=pre_locate)
        return self._om_pen_apply_leniently(source, specs_tree, pre_locate=pre_locate)

    def _om_pen_apply_leniently(self, source, specs_tree, pre_locate=None, failures=None):
        """ Apply the specs one by one, keeping track of the ones that fail. """
        specs = list(specs_tree) if specs_tree.tag == 'data' else [specs_tree]
        for index, spec in enumerate(specs):
            if not isinstance(spec.tag, str):
                continue
            try:
                source = self.with_context(**{STRICT_KEY: True}).apply_inheritance_specs(
                    source, spec, pre_locate=pre_locate)
            except (ValidationError, ValueError) as error:
                _logger.info("om_pen: change skipped on %s: %s", self.display_name or self.id, error)
                if failures is not None:
                    failures.append(index)
        return source


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
                arch = view.with_context(**{DRAFT_OPTION: True})._om_pen_apply_leniently(arch, specs)
        return arch, view
