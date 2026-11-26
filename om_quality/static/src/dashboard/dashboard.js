import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const PERIODS = [
    [7, _t("7 days")],
    [30, _t("30 days")],
    [90, _t("90 days")],
    [365, _t("12 months")],
];

/**
 * Quality overview: what waits, how the checks go and where they fail, and the
 * non-conformances by stage. Every figure opens the records behind it.
 */
export class QualityDashboard extends Component {
    static template = "om_quality.QualityDashboard";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periods = PERIODS;
        this.state = proxy({ days: 30, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("om.quality.dashboard", "get_data", [this.state.days]);
    }

    async setPeriod(days) {
        this.state.days = days;
        await this.load();
    }

    get doneDomain() {
        return [["state", "in", ["passed", "failed"]], ["date_done", ">=", this.state.data.since]];
    }

    open(model, name, domain, context = {}, views = [[false, "list"], [false, "form"]]) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            context,
            views,
        });
    }

    openChecks(name, domain) {
        this.open("om.quality.check", name, domain, {}, [[false, "list"], [false, "kanban"], [false, "form"], [false, "pivot"], [false, "graph"]]);
    }

    openTodo() {
        this.openChecks(_t("Checks to Do"), [["state", "=", "todo"]]);
    }

    openWaiting() {
        this.openChecks(_t("Checks Holding a Document"), [["blocking_pending", "=", true]]);
    }

    openDone() {
        this.openChecks(_t("Checks Done"), this.doneDomain);
    }

    openFailed() {
        this.openChecks(_t("Failed Checks"), [["state", "=", "failed"], ["date_done", ">=", this.state.data.since]]);
    }

    openRow(field, row, failedOnly = false) {
        const domain = failedOnly
            ? [["state", "=", "failed"], ["date_done", ">=", this.state.data.since]]
            : this.doneDomain;
        this.openChecks(row.name, [...domain, [field, "=", row.id]]);
    }

    openAlerts(stage) {
        const domain = stage ? [["stage_id", "=", stage.id]] : [["is_closed", "=", false]];
        this.open("om.quality.alert", stage ? stage.name : _t("Open Non-conformances"), domain, {},
            [[false, "kanban"], [false, "list"], [false, "form"]]);
    }

    openActions(late) {
        const domain = [["state", "=", "open"]];
        if (late) {
            domain.push(["date_deadline", "<", luxon.DateTime.now().toISODate()]);
        }
        this.open("om.quality.action", late ? _t("Late Actions") : _t("Open Actions"), domain);
    }

    get rateSections() {
        return [
            { title: _t("By product"), rows: this.state.data.products, field: "product_id" },
            { title: _t("By vendor or customer"), rows: this.state.data.partners, field: "partner_id" },
        ];
    }

    rateClass(rate) {
        return rate >= 95 ? "text-success" : rate >= 80 ? "text-warning" : "text-danger";
    }

    barWidth(row, rows) {
        const max = Math.max(...rows.map((r) => r.count || r.failed || 0), 1);
        return `width: ${Math.round((100 * (row.count || row.failed || 0)) / max)}%`;
    }
}

registry.category("actions").add("om_quality_dashboard", QualityDashboard);
