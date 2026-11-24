import copy
import logging

from lxml import etree

from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def uninstall_hook(env):
    """ Keep the generated views when the module goes: they are the user's work.

    While Pen is installed, a change that no longer fits its view (after a module
    update) is skipped. Without Pen it would make the view fail, and the next module
    update with it, so the changes that do not fit any more are left out of the
    views that stay, and a view none of whose changes fit is switched off.
    """
    customizations = env['om.pen.view'].sudo().with_context(active_test=False).search([])
    views = customizations.custom_view_id.with_context(om_pen_strict=True)
    for view in views:
        if not view.active or not view.inherit_id:
            continue
        try:
            _keep_fitting_changes(view)
        except (ValidationError, UserError, ValueError, etree.LxmlError) as error:
            _logger.warning("om_pen: view %s switched off on uninstall: %s", view.id, error)
            view.active = False


def _keep_fitting_changes(view):
    source = view.with_context(ir_ui_view_tree_cut_off_view=view)._get_combined_arch()
    arch = etree.fromstring(view.arch)
    specs = [spec for spec in (list(arch) if arch.tag == 'data' else [arch]) if isinstance(spec.tag, str)]
    kept = []
    for spec in specs:
        try:
            # applying moves the nodes of the spec into the source: apply a copy
            source = view.apply_inheritance_specs(source, copy.deepcopy(spec))
        except (ValidationError, ValueError):
            continue
        kept.append(spec)
    if not kept:
        view.active = False
    elif len(kept) != len(specs):
        data = etree.Element('data')
        data.extend(kept)
        view.arch = etree.tostring(data, encoding='unicode')
