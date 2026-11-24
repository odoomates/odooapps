import re

from lxml import etree

from odoo import Command, _, api, models
from odoo.exceptions import UserError

from . import om_pen_arch as archlib
from .om_pen_studio import new_name


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    # ------------------------------------------------------------------
    # models
    # ------------------------------------------------------------------

    @api.model
    def _model_name_for(self, label):
        slug = re.sub(r'[^a-z0-9]+', '_', (label or '').lower()).strip('_')[:40] or 'model'
        name = 'x_%s' % slug
        candidate, suffix = name, 2
        while candidate in self.env or self.env['ir.model'].sudo().search_count([('model', '=', candidate)]):
            candidate = '%s_%s' % (name, suffix)
            suffix += 1
        return candidate

    @api.model
    def _create_model(self, label, fields_=None, mail=False, activity=False, order=False):
        """ A manual model with a name field, readable and writable by every user. """
        self._check_admin()
        model = self._model_name_for(label)
        vals = {
            'name': label,
            'model': model,
            'state': 'manual',
            'field_id': [Command.create({
                'name': 'x_name', 'field_description': _("Name"), 'ttype': 'char',
                'required': True, 'state': 'manual'})] + [Command.create(dict(field, state='manual'))
                                                         for field in (fields_ or [])],
        }
        IrModel = self.env['ir.model'].sudo()
        if 'is_mail_thread' in IrModel._fields:
            vals['is_mail_thread'] = mail
            vals['is_mail_activity'] = activity
        if order:
            vals['order'] = order
        record = IrModel.with_context(update_custom_fields=True).create(vals)
        self.env['ir.access'].sudo().create([{
            'name': '%s user' % model,
            'model_id': record.id,
            'group_id': self.env.ref('base.group_user').id,
            'operation': 'crud',
        }])
        return model

    # ------------------------------------------------------------------
    # stages
    # ------------------------------------------------------------------

    @api.model
    def studio_add_stages(self, customization_id, revision, show_hidden=False):
        """ Stages in one click: a stage model, a link to it, a status bar.

        The form gets the status bar in its header; a kanban of the model is grouped by
        stage from then on.
        """
        customization = self._customization(customization_id)
        self._check_admin()
        model = customization.model
        if 'x_stage_id' in self.env[model]._fields:
            raise UserError(_("This model already has stages."))
        stage_model = self._stage_model(model)
        self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True).create({
            'name': 'x_stage_id', 'field_description': _("Stage"), 'model': model,
            'model_id': self.env['ir.model']._get_id(model), 'ttype': 'many2one',
            'relation': stage_model, 'on_delete': 'restrict', 'state': 'manual',
            # every stage shows as a kanban column, even an empty one
            'group_expand': True,
        })
        first = self.env[stage_model].search([], order='x_sequence, id', limit=1)
        self.env['ir.default'].sudo().set(model, 'x_stage_id', first.id)
        # records made before the stages existed start in the first one
        self.env[model].sudo().with_context(active_test=False).search([]).write({'x_stage_id': first.id})
        self._group_kanban_by(model, 'x_stage_id')
        return self._statusbar_change(customization, revision, 'x_stage_id', show_hidden)

    @api.model
    def _stage_model(self, model):
        label = _("%s Stage", self.env['ir.model']._get(model).name)
        stage_model = self._create_model(label, [
            {'name': 'x_sequence', 'field_description': _("Sequence"), 'ttype': 'integer'},
            {'name': 'x_fold', 'field_description': _("Folded"), 'ttype': 'boolean'},
        ], order='x_sequence, id')
        self.env[stage_model].sudo().create([
            {'x_name': _("New"), 'x_sequence': 1},
            {'x_name': _("In Progress"), 'x_sequence': 2},
            {'x_name': _("Done"), 'x_sequence': 3, 'x_fold': True},
        ])
        return stage_model

    @api.model
    def _statusbar_change(self, customization, revision, field_name, show_hidden):
        arch, _view, _failed = self._draft_arch(customization)
        header = arch.find('header')
        node = etree.Element('field', name=field_name, widget='statusbar', options="{'clickable': '1'}")
        if header is not None:
            spec = archlib.spec(archlib.locator(header, arch), 'inside', node)
        else:
            new_header = etree.Element('header')
            new_header.append(node)
            spec = self._first_child_spec(arch, arch, new_header)
        return self._push_and_render(customization, revision, [spec], _("Added stages"), show_hidden)

    @api.model
    def _group_kanban_by(self, model, field_name):
        """ Group the model's kanban by `field_name`, as a published change. """
        view_id = self.env['ir.ui.view'].default_view(model, 'kanban')
        if not view_id:
            return
        customization = self.env['om.pen.view']._get_or_create(model, view_id, 'kanban')
        spec = archlib.attributes_spec('/kanban', {'default_group_by': field_name})
        ops = list(customization.published_ops or []) + [
            {'spec': archlib.to_string(spec), 'label': _("Grouped by stage")}]
        customization.write({'published_ops': ops, 'draft_ops': ops})

    @api.model
    def _first_child_spec(self, arch, parent, element):
        """ Insert `element` as the first child of `parent`. """
        first = next((child for child in parent if archlib.is_element(child)), None)
        if first is None:
            return archlib.spec(archlib.locator(parent, arch), 'inside', element)
        return archlib.spec(archlib.locator(first, arch), 'before', element)

    @api.model
    def _push_and_render(self, customization, revision, specs, label, show_hidden):
        if revision and revision != customization._revision():
            raise UserError(_("The view was changed elsewhere in the meantime. Reload the Studio."))
        with self.env.cr.savepoint():
            customization._push_ops(specs, label)
            result = self._view_payload(customization, show_hidden=show_hidden, strict=True)
        return result

    # ------------------------------------------------------------------
    # buttons
    # ------------------------------------------------------------------

    @api.model
    def studio_smart_button_targets(self, model):
        """ Models linking to `model`, which a smart button can count and open. """
        self._check()
        links = self.env['ir.model.fields'].search([
            ('relation', '=', model), ('ttype', '=', 'many2one'), ('store', '=', True)])
        result = []
        for link in links:
            if link.model not in self.env or self.env[link.model]._transient or self.env[link.model]._abstract:
                continue
            result.append({
                'field': link.name,
                'model': link.model,
                'label': '%s (%s)' % (link.model_id.name, link.field_description),
            })
        return sorted(result, key=lambda item: item['label'])

    @api.model
    def studio_add_smart_button(self, customization_id, revision, values, show_hidden=False):
        """ A button counting the records linked to this one, and opening them. """
        customization = self._customization(customization_id)
        self._check_admin()
        model = customization.model
        target_model = values.get('model')
        link = values.get('field')
        if target_model not in self.env or link not in self.env[target_model]._fields:
            raise UserError(_("Pick what the button counts."))
        field = self.env[target_model]._fields[link]
        if field.type != 'many2one' or field.comodel_name != model:
            raise UserError(_("%(field)s does not link %(model)s to this record.", field=link, model=target_model))
        label = values.get('label') or self.env['ir.model']._get(target_model).name
        count_name = self.env['om.pen.view']._field_name_for(model, '%s count' % label)
        code = ("for record in self:\n"
                "    record[%r] = self.env[%r].search_count([(%r, '=', record.id)])") % (
                    count_name, target_model, link)
        self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True).create({
            'name': count_name, 'field_description': label, 'model': model,
            'model_id': self.env['ir.model']._get_id(model), 'ttype': 'integer',
            'compute': code, 'depends': '', 'store': False, 'readonly': True, 'state': 'manual',
        })
        action = self.env['ir.actions.act_window'].sudo().create({
            'name': label,
            'res_model': target_model,
            'view_mode': 'list,form',
            'domain': "[(%r, '=', active_id)]" % link,
            'context': "{'default_%s': active_id}" % link,
        })
        button = etree.Element('button', type='action', name=str(action.id), icon=values.get('icon') or 'view_list')
        button.set('class', 'oe_stat_button')
        etree.SubElement(button, 'field', name=count_name, widget='statinfo', string=label)

        arch, _view, _failed = self._draft_arch(customization)
        box = arch.xpath("//div[@name='button_box']")
        if box:
            spec = archlib.spec(archlib.locator(box[0], arch), 'inside', button)
        else:
            sheet = arch.find('.//sheet')
            new_box = etree.Element('div', name='button_box')
            new_box.set('class', 'oe_button_box')
            new_box.append(button)
            spec = self._first_child_spec(arch, sheet if sheet is not None else arch, new_box)
        return self._push_and_render(customization, revision, [spec], _("Added smart button %s", label), show_hidden)

    @api.model
    def studio_add_header_button(self, customization_id, revision, values, show_hidden=False):
        """ A button in the form's header, running a server action. """
        customization = self._customization(customization_id)
        model = customization.model
        action_id = values.get('action_id')
        if not action_id and values.get('field'):
            action_id = self._update_action(model, values).id
        element = self._build_button(model, {**values, 'action_id': action_id})
        if values.get('invisible'):
            archlib.check_expression(values['invisible'])
            element.set('invisible', values['invisible'])
        arch, _view, _failed = self._draft_arch(customization)
        header = arch.find('header')
        if header is not None:
            spec = archlib.spec(archlib.locator(header, arch), 'inside', element)
        else:
            new_header = etree.Element('header')
            new_header.append(element)
            spec = self._first_child_spec(arch, arch, new_header)
        return self._push_and_render(customization, revision, [spec],
                                     _("Added button %s", element.get('string')), show_hidden)

    @api.model
    def _update_action(self, model, values):
        """ A server action setting one field of the record to a value. """
        self._check_admin()
        field = self.env['ir.model.fields']._get(model, values['field'])
        if not field:
            raise UserError(_("%(model)s has no field %(field)s.", model=model, field=values['field']))
        vals = {
            'name': values.get('string') or _("Set %s", field.field_description),
            'model_id': self.env['ir.model']._get_id(model),
            'state': 'object_write',
            'update_field_id': field.id,
            'update_path': field.name,
            'evaluation_type': 'value',
            'value': str(values.get('value') or ''),
        }
        if field.ttype == 'many2one' and values.get('value'):
            vals['resource_ref'] = '%s,%s' % (field.relation, int(values['value']))
        server = self.env['ir.actions.server'].sudo()
        vals = {key: value for key, value in vals.items() if key in server._fields}
        return server.create(vals)

    @api.model
    def studio_enable_chatter(self, customization_id, revision, show_hidden=False):
        """ A chatter for the model, and on its form. """
        customization = self._customization(customization_id)
        self._check_admin()
        model = customization.model
        if not self._has_mail(model):
            ir_model = self.env['ir.model'].sudo()._get(model)
            if ir_model.state != 'manual' or 'is_mail_thread' not in ir_model._fields:
                raise UserError(_("Only a model made in the Studio can be given a chatter."))
            ir_model.write({'is_mail_thread': True, 'is_mail_activity': True})
        arch, _view, _failed = self._draft_arch(customization)
        if arch.xpath('//chatter'):
            raise UserError(_("The form already has a chatter."))
        spec = archlib.spec('/%s' % arch.tag, 'inside', etree.Element('chatter'))
        return self._push_and_render(customization, revision, [spec], _("Added the chatter"), show_hidden)

    @api.model
    def _unique_name(self, kind):
        return new_name(kind)
