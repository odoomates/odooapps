import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "om.report.design";

/**
 * A published report on screen, for the records of its filter (or the
 * records it was opened for), with the same layout as its PDF.
 */
export class ReportViewer extends Component {
    static template = "om_report_designer.Viewer";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.params = this.props.action.params || {};
        this.designId = this.params.design_id;
        this.state = proxy({ data: null, loading: false, zoom: 1 });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(MODEL, "viewer_load", [[this.designId]], {
                record_ids: this.params.record_ids || null,
            });
        } finally {
            this.state.loading = false;
        }
    }

    get html() {
        return markup(this.state.data?.html || "");
    }

    get sheetStyle() {
        const settings = this.state.data.settings;
        return [
            `width:${settings.page_width}mm`,
            `padding:${settings.margin_top}mm ${settings.margin_right}mm ${settings.margin_bottom}mm ${settings.margin_left}mm`,
            `zoom:${this.state.zoom}`,
        ].join(";");
    }

    get countLabel() {
        const data = this.state.data;
        if (data.count < data.total) {
            return _t("The first %(count)s of %(total)s records", { count: data.count, total: data.total });
        }
        return data.count === 1 ? _t("1 record") : _t("%s records", data.count);
    }

    async printPdf() {
        const action = await this.orm.call(MODEL, "viewer_print", [[this.designId], this.state.data.ids]);
        await this.action.doAction(action);
    }

    openDesigner() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "om_report_designer",
            name: this.state.data.name,
            params: { design_id: this.designId },
        });
    }

    setZoom(value) {
        this.state.zoom = Math.min(3, Math.max(0.25, Math.round(value * 100) / 100));
    }
}

registry.category("actions").add("om_report_designer_viewer", ReportViewer);
