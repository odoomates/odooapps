# Part of Odoo2XL - Odoo Excel Reports (om_excel_reports). License: LGPL-3.
from odoo import _, api, models
from odoo.exceptions import UserError

from ..lib.html_to_xlsx import ConverterOptions, convert_report_html

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def is_pdf_report_type(report_type):
    """Odoo 20: PDF reports are ``qweb-pdf`` or ``qweb-pdf-<engine>`` (e.g. ``qweb-pdf-wkhtmltopdf``)."""
    return bool(report_type) and report_type.startswith('qweb-pdf')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _render_excel(self, report_ref, res_ids=None, data=None):
        """Render a PDF report as an .xlsx file. Returns ``(content, 'xlsx')``."""
        report = self._get_report(report_ref)
        if not is_pdf_report_type(report.report_type):
            raise UserError(_("Only PDF reports can be exported to Excel: '%s'.", report.name))
        html, _report_type = self._render_qweb_html(report_ref, res_ids, data=data)
        lang = self.env['res.lang']._lang_get(self.env.lang or self.env.user.lang or 'en_US')
        options = ConverterOptions(
            decimal_point=lang.decimal_point if lang else '.',
            thousands_sep=lang.thousands_sep if lang else ',',
            date_format=lang.date_format if lang else '%m/%d/%Y',
            title=report.name,
        )
        try:
            return convert_report_html(html, options), 'xlsx'
        except ValueError as exc:
            raise UserError(str(exc)) from exc
