# Marks every method of the exported model so the field guard hides hidden
# fields from the Export dialog and refuses them in the file.
import json

from odoo import http

from odoo.addons.web.controllers.export import CSVExport, ExcelExport, Export

from ..models.field_guard import mark_rpc_entry


def mark_export(data):
    try:
        model = json.loads(data).get('model')
    except (TypeError, ValueError):
        model = None
    if model:
        mark_rpc_entry(model, '*')


class ExportAccess(Export):

    @http.route()
    def get_fields(self, model, domain, prefix='', parent_name='', import_compat=True,
                   parent_field_type=None, parent_field=None, exclude=None):
        mark_rpc_entry(model, '*')
        return super().get_fields(model, domain, prefix=prefix, parent_name=parent_name,
                                  import_compat=import_compat, parent_field_type=parent_field_type,
                                  parent_field=parent_field, exclude=exclude)


class CSVExportAccess(CSVExport):

    @http.route()
    def web_export_csv(self, data):
        mark_export(data)
        return super().web_export_csv(data)


class ExcelExportAccess(ExcelExport):

    @http.route()
    def web_export_xlsx(self, data):
        mark_export(data)
        return super().web_export_xlsx(data)
