from odoo import models
from odoo.tools.pdf import merge_pdf

RECEIPT_REPORT = 'om_whatsapp_pos.report_pos_order_receipt'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """ The receipt of a POS order as a PDF: the picture of the receipt
        the POS prints, on a page of its size, followed by the invoice when
        the order is invoiced. """
        report = self._get_report(report_ref)
        if report.report_name != RECEIPT_REPORT:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        pdfs = []
        for order in self.env['pos.order'].browse(res_ids):
            pdfs.append(order._om_whatsapp_receipt_pdf())
            if order.account_move:
                pdfs.append(super()._render_qweb_pdf('account.account_invoices', order.account_move.ids[:1])[0])
        return merge_pdf(pdfs) if len(pdfs) > 1 else pdfs[0], 'pdf'
