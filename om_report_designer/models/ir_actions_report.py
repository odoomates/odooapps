from odoo import fields, models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    om_rd_design_id = fields.Many2one('om.report.design', string='Report Design', ondelete='cascade',
                                      index='btree_not_null', readonly=True)

    def _get_rendering_context(self, report, docids, data):
        data = super()._get_rendering_context(report, docids, data)
        if report.om_rd_design_id:
            mode = 'pdf' if data.get('report_type') == 'pdf' else 'html'
            data['om_rd_html'] = report.om_rd_design_id._render_html(data['docs'], mode)
        return data
