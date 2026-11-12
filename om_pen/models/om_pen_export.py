import base64
import io
import re
import zipfile

from lxml import etree

from odoo import _, models
from odoo.exceptions import UserError

# fields of ir.model.fields worth carrying over; anything else is either derived or
# meaningless on a fresh database
EXPORTED_FIELD_ATTRIBUTES = (
    'field_description', 'ttype', 'relation', 'relation_field', 'required', 'readonly',
    'help', 'copied', 'index', 'store', 'currency_field', 'on_delete', 'domain',
)

MANIFEST = '''{
    'name': %(name)r,
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': "View customizations exported from %(database)s",
    'description': """
Customizations exported by om_pen.

Installing this module recreates the custom fields and the inherited views it carries,
so a database can be set up the same way without repeating the work by hand.
""",
    'author': 'Odoo Mates',
    'depends': %(depends)r,
    'data': [
        'data/ir_model_fields.xml',
        'views/customizations.xml',
    ],
    'license': 'LGPL-3',
}
'''


class OmPenView(models.Model):
    _inherit = 'om.pen.view'

    def action_export_module(self):
        """ Package the selected customizations as an installable module.

        This is what makes a customization portable: the rules live in one database,
        but the fields and views they produce can be replayed anywhere.
        """
        self._check_customizer()
        records = self.filtered('custom_view_id')
        if not records:
            raise UserError(_("None of the selected customizations produced a view yet."))

        module = 'om_pen_export'
        fields_doc, field_modules = records._export_fields_document()
        views_doc, view_modules = records._export_views_document()
        depends = sorted({'base'} | field_modules | view_modules)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('%s/__init__.py' % module, '')
            archive.writestr('%s/__manifest__.py' % module, MANIFEST % {
                'name': "Exported View Customizations",
                'database': self.env.cr.dbname,
                'depends': depends,
            })
            archive.writestr('%s/data/ir_model_fields.xml' % module, fields_doc)
            archive.writestr('%s/views/customizations.xml' % module, views_doc)

        attachment = self.env['ir.attachment'].create({
            'name': '%s.zip' % module,
            'type': 'binary',
            'datas': base64.b64encode(buffer.getvalue()),
            'mimetype': 'application/zip',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _export_fields_document(self):
        """ The custom fields the exported views reference. """
        root = etree.Element('odoo')
        data = etree.SubElement(root, 'data', noupdate="1")
        modules = set()

        for field in self._exported_fields():
            model_xmlid = field.model_id.get_external_id().get(field.model_id.id)
            if not model_xmlid:
                raise UserError(_(
                    "The model %s has no external id, so its custom fields cannot be"
                    " exported.") % field.model)
            modules.add(model_xmlid.split('.')[0])

            record = etree.SubElement(
                data, 'record', id=_xmlid_for_field(field), model='ir.model.fields')
            etree.SubElement(record, 'field', name='name').text = field.name
            etree.SubElement(record, 'field', name='model').text = field.model
            etree.SubElement(record, 'field', name='model_id', ref=model_xmlid)
            etree.SubElement(record, 'field', name='state').text = 'manual'
            for attribute in EXPORTED_FIELD_ATTRIBUTES:
                value = field[attribute]
                if value in (False, '', None):
                    continue
                etree.SubElement(record, 'field', name=attribute).text = str(value)
            if field.ttype in ('selection', 'reference'):
                for option in field.selection_ids:
                    etree.SubElement(
                        data, 'record',
                        id='%s_%s' % (_xmlid_for_field(field), _slug(option.value)),
                        model='ir.model.fields.selection',
                    ).extend([
                        _field_element('field_id', ref=_xmlid_for_field(field)),
                        _field_element('value', text=option.value),
                        _field_element('name', text=option.name),
                        _field_element('sequence', text=str(option.sequence)),
                    ])

        return _pretty(root), modules

    def _exported_fields(self):
        """ Custom fields named by any of these customizations. """
        names = set()
        for record in self:
            names |= {rule.field_name for rule in record.rule_ids}
        if not names:
            return self.env['ir.model.fields']
        return self.env['ir.model.fields'].search([
            ('model', 'in', self.mapped('model')),
            ('name', 'in', list(names)),
            ('state', '=', 'manual'),
        ])

    def _export_views_document(self):
        root = etree.Element('odoo')
        data = etree.SubElement(root, 'data', noupdate="1")
        modules = set()

        for record in self:
            inherited = record.view_id
            view_xmlid = inherited.get_external_id().get(inherited.id)
            if not view_xmlid:
                raise UserError(_(
                    "The view %s has no external id, so a customization of it cannot be"
                    " exported.") % inherited.display_name)
            modules.add(view_xmlid.split('.')[0])

            view = etree.SubElement(
                data, 'record', id='view_customization_%s' % record.id, model='ir.ui.view')
            etree.SubElement(view, 'field', name='name').text = record.custom_view_id.name
            etree.SubElement(view, 'field', name='model').text = record.model
            etree.SubElement(view, 'field', name='inherit_id', ref=view_xmlid)
            etree.SubElement(view, 'field', name='mode').text = 'extension'
            etree.SubElement(view, 'field', name='priority').text = str(
                record.custom_view_id.priority)
            arch = etree.SubElement(view, 'field', name='arch')
            arch.set('type', 'xml')
            arch.append(etree.fromstring(record._render_arch()))

        return _pretty(root), modules


def _field_element(name, text=None, ref=None):
    element = etree.Element('field', name=name)
    if ref:
        element.set('ref', ref)
    if text is not None:
        element.text = text
    return element


def _slug(value):
    return re.sub(r'[^a-z0-9]+', '_', (value or '').lower()).strip('_') or 'value'


def _xmlid_for_field(field):
    return 'field_%s_%s' % (field.model.replace('.', '_'), field.name)


def _pretty(root):
    etree.indent(root, space="    ")
    return etree.tostring(root, pretty_print=True, xml_declaration=True,
                          encoding='utf-8').decode()
