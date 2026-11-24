from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmDynamicReportCustom(models.AbstractModel):
    """A financial report of the user (Accounting > Configuration > Financial
    Reports) over a period, opened from the menu added to it: the ``variant``
    option is the id of the report."""
    _name = 'om.dynamic.report.custom'
    _inherit = 'om.dynamic.report.financial'
    _description = 'Dynamic Custom Financial Report'

    _report_name = 'Financial Report'
    _report_description = _lt("A financial report set up in Accounting.")
    # opened from its own menu, not listed in the switcher of the accounting reports
    _report_app = False
    _report_icon = 'account_tree'

    @api.model
    def _om_prepare(self, options):
        report = super()._om_prepare(options)
        variant = options.get('variant')
        root_id = int(variant) if str(variant or '').isdigit() else False
        return report.with_context(om_financial_report_id=root_id)

    @api.model
    def _odr_root_report(self):
        root_id = self.env.context.get('om_financial_report_id')
        root = self.env['account.financial.report'].browse(root_id).exists() if root_id else False
        return root if root and not root.parent_id else self.env['account.financial.report']

    @api.model
    def _om_report_title(self):
        return self._odr_root_report().name or self.env._("Financial Report")

    @api.model
    def _odr_closes(self, root):
        return root.dynamic_total


class OmDynamicReportCustomAsOf(models.AbstractModel):
    """A financial report of the user at a date, as a balance sheet is."""
    _name = 'om.dynamic.report.custom.as.of'
    _inherit = 'om.dynamic.report.custom'
    _description = 'Dynamic Custom Financial Report at a Date'

    _report_date_mode = 'as_of'
    _report_default_preset = 'today'

    @api.model
    def _om_compare_choices(self):
        return [
            {'key': 'previous_year', 'label': self.env._("Same date last year")},
            {'key': 'previous_period', 'label': self.env._("Previous month end")},
        ]
