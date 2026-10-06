# Mark the calls a client makes, keep the address of the RPC clients, and log
# the sign-outs and the reports printed.
import json

from odoo import http
from odoo.http import request

from odoo.addons.base.controllers import rpc as base_rpc
from odoo.addons.web.controllers.dataset import DataSet
from odoo.addons.web.controllers.export import CSVExport, ExcelExport, Export
from odoo.addons.web.controllers.report import ReportController
from odoo.addons.web.controllers.session import Session

from ..models.client_call import RPC_ADDRESS, mark_rpc_entry


def mark_export(data):
    try:
        model = json.loads(data).get('model')
    except (TypeError, ValueError, AttributeError):
        model = None
    if model:
        mark_rpc_entry(model, '*')


def with_address(dispatch_rpc):
    """ Keep the client's address: ``dispatch_rpc`` unbinds the request. """
    if getattr(dispatch_rpc, 'om_with_address', False):
        return dispatch_rpc

    def dispatch(*args, **kwargs):
        token = RPC_ADDRESS.set(request.httprequest.remote_addr if request else None)
        try:
            return dispatch_rpc(*args, **kwargs)
        finally:
            RPC_ADDRESS.reset(token)
    dispatch.om_with_address = True
    return dispatch


# the RPC routes run without a database, so overriding their controllers would
# not apply: wrap the function they call instead
base_rpc.dispatch_rpc = with_address(base_rpc.dispatch_rpc)


class DataSetAudit(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        mark_rpc_entry(model, method)
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs):
        mark_rpc_entry(model, method)
        return super().call_button(model, method, args, kwargs)


class ExportAudit(Export):

    @http.route()
    def get_fields(self, model, prefix='', parent_name='', import_compat=True,
                   parent_field_type=None, parent_field=None, exclude=None):
        mark_rpc_entry(model, '*')
        return super().get_fields(model, prefix=prefix, parent_name=parent_name,
                                  import_compat=import_compat, parent_field_type=parent_field_type,
                                  parent_field=parent_field, exclude=exclude)


class CSVExportAudit(CSVExport):

    @http.route()
    def web_export_csv(self, data):
        mark_export(data)
        return super().web_export_csv(data)


class ExcelExportAudit(ExcelExport):

    @http.route()
    def web_export_xlsx(self, data):
        mark_export(data)
        return super().web_export_xlsx(data)


class SessionAudit(Session):

    @http.route()
    def destroy(self):
        request.env['ir.http']._om_log_logout()
        return super().destroy()

    @http.route()
    def logout(self, redirect='/web'):
        request.env['ir.http']._om_log_logout()
        return super().logout(redirect=redirect)


class ReportAudit(ReportController):

    @http.route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        response = super().report_routes(reportname, docids=docids, converter=converter, **data)
        report = request.env['ir.actions.report'].sudo()._get_report_from_name(reportname)
        model = request.env.get(report.model) if report else None
        if model is not None and model._om_audit('print'):
            ids = [int(i) for i in (docids or '').split(',') if i.strip().isdigit()]
            request.env['om.user.audit.log']._om_log(
                'print', model=report.model, method=reportname, record_ids=ids,
                res_id=ids[0] if len(ids) == 1 else False,
                res_name=model.browse(ids[0]).sudo().display_name if len(ids) == 1 else False,
                detail=report.name)
        return response
