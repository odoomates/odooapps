from lxml import etree

from odoo import fields, models
from odoo.tools.safe_eval import safe_eval

GANTT_VALID_ATTRIBUTES = {
    '__validate__',  # ir.ui.view implementation detail
    'class',
    'js_class',
    'string',
    'sample',
    'create',
    'edit',
    'delete',
    'plan',
    'date_start',
    'date_stop',
    'default_scale',
    'scales',
    'default_group_by',
    'default_order',
    'color',
    'progress',
    'consolidation',
    'consolidation_max',
    'precision',
    'thumbnails',
    'dependency_field',
    'total_row',
    'display_unavailability',
    'pill_label',
    'form_view_id',
    'progress_bar',
    'empty_row_labels',
}
GANTT_DECORATIONS = {
    'decoration-info', 'decoration-success', 'decoration-warning', 'decoration-danger',
    'decoration-muted', 'decoration-bf', 'decoration-it', 'decoration-striped',
}
GANTT_SCALES = {'day', 'week', 'month', 'year'}
GANTT_FIELD_ATTRIBUTES = ('date_start', 'date_stop', 'color', 'progress', 'consolidation', 'dependency_field')


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('gantt', "Gantt")])

    def _is_qweb_based_view(self, view_type):
        return super()._is_qweb_based_view(view_type) or view_type == 'gantt'

    def _get_view_info(self):
        return {'gantt': {'icon': 'view_timeline'}} | super()._get_view_info()

    def _postprocess_tag_gantt(self, node, name_manager, node_info):
        for attribute in GANTT_FIELD_ATTRIBUTES:
            if fname := node.get(attribute):
                name_manager.has_field(node, fname, node_info)
        for fname in (node.get('default_group_by') or '').split(','):
            if fname.strip():
                name_manager.has_field(node, fname.strip(), node_info)

    def _validate_tag_gantt(self, node, name_manager, node_info):
        if not node_info['validate']:
            return
        env = self.env
        model = name_manager.model
        for attribute in ('date_start', 'date_stop'):
            if not node.get(attribute):
                self._raise_view_error(env._("Gantt view must define the attribute %s.", attribute), node)
        for attribute in GANTT_FIELD_ATTRIBUTES:
            fname = node.get(attribute)
            if not fname:
                continue
            field = model._fields.get(fname)
            if not field:
                self._raise_view_error(
                    env._("Field %(field)s used in attribute %(attribute)s does not exist on %(model)s.",
                          field=fname, attribute=attribute, model=model._name), node)
            if attribute in ('date_start', 'date_stop') and field.type not in ('date', 'datetime'):
                self._raise_view_error(
                    env._("Attribute %s must be a date or datetime field.", attribute), node)
            if attribute == 'dependency_field' and (field.type != 'many2many' or field.comodel_name != model._name):
                self._raise_view_error(
                    env._("Attribute dependency_field must be a many2many field to %s.", model._name), node)
            name_manager.has_field(node, fname, node_info)

        scales = {scale.strip() for scale in (node.get('scales') or '').split(',') if scale.strip()}
        if scales - GANTT_SCALES:
            self._raise_view_error(
                env._("Invalid scales %(scales)s, use day, week, month or year.",
                      scales=', '.join(sorted(scales - GANTT_SCALES))), node)
        default_scale = node.get('default_scale')
        if default_scale and (default_scale not in GANTT_SCALES or (scales and default_scale not in scales)):
            self._raise_view_error(env._("Invalid default_scale %s.", default_scale), node)
        for fname in (node.get('progress_bar') or '').split(','):
            if fname.strip() and fname.strip() not in model._fields:
                self._raise_view_error(
                    env._("Field %(field)s used in attribute progress_bar does not exist on %(model)s.",
                          field=fname.strip(), model=model._name), node)
        for attribute in GANTT_DECORATIONS & set(node.attrib):
            self._validate_expression(node, name_manager, node.get(attribute), attribute, node_info)
        for attribute in ('consolidation_max', 'precision', 'thumbnails', 'empty_row_labels'):
            if node.get(attribute):
                try:
                    value = safe_eval(node.get(attribute))
                except (ValueError, SyntaxError, NameError):
                    value = None
                if not isinstance(value, dict):
                    self._raise_view_error(
                        env._("Attribute %s must be a dictionary.", attribute), node)

        templates_count = 0
        for child in node.iterchildren(tag=etree.Element):
            if child.tag == 'templates':
                templates_count += 1
                if templates_count > 1:
                    self._raise_view_error(env._("Gantt view can contain only one templates tag."), child)
            elif child.tag != 'field':
                self._raise_view_error(
                    env._("Gantt child can only be field or templates, got %s.", child.tag), child)

        remaining = set(node.attrib) - GANTT_VALID_ATTRIBUTES - GANTT_DECORATIONS
        if remaining:
            self._raise_view_error(
                env._("Invalid attributes (%(invalid)s) in gantt view. Attributes must be in (%(valid)s)",
                      invalid=', '.join(sorted(remaining)),
                      valid=', '.join(sorted((GANTT_VALID_ATTRIBUTES | GANTT_DECORATIONS) - {'__validate__'}))), node)
