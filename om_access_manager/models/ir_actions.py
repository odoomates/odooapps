# get_bindings() is per user and uncached, so hidden reports and actions leave
# the menus there. Enforcement is in controllers/action.py and the renders below.
from odoo import _, api, models


class IrActionsActions(models.Model):
    _inherit = 'ir.actions.actions'

    @api.model
    def get_bindings(self, model_name):
        result = super().get_bindings(model_name)
        rules = self.env['om.access.profile']._current_rules()
        if not rules.enabled:
            return result
        kept = {}
        for action_type, actions in result.items():
            if action_type == 'report' and rules.model_flag(model_name, 'hide_print'):
                continue
            if action_type == 'action' and rules.model_flag(model_name, 'hide_action_menu'):
                continue
            visible = [
                action for action in actions
                if not (rules.hides_report(action['id']) or rules.hides_action(action['id']))
            ]
            if visible:
                kept[action_type] = visible
        return kept


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _om_check_report_access(self, report_ref):
        rules = self.env['om.access.profile']._current_rules()
        if not rules.enabled:
            return
        report = self._get_report(report_ref)
        if rules.hides_report(report.id) or rules.model_flag(report.model, 'hide_print'):
            raise self.env['om.access.profile']._om_refusal(_(
                "Your access profile does not allow printing '%s'.",
                report.name), model=report.model, method=report.report_name)

    # The report routes call _render_qweb_pdf() directly, bypassing _render(),
    # so each entry point carries its own check.
    def _render(self, report_ref, res_ids, data=None):
        self._om_check_report_access(report_ref)
        return super()._render(report_ref, res_ids, data=data)

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        self._om_check_report_access(report_ref)
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    def _render_qweb_html(self, report_ref, docids, data=None):
        self._om_check_report_access(report_ref)
        return super()._render_qweb_html(report_ref, docids, data=data)

    def _render_qweb_text(self, report_ref, docids, data=None):
        self._om_check_report_access(report_ref)
        return super()._render_qweb_text(report_ref, docids, data=data)
