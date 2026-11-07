import { Component, onWillStart, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// the user fields people limit by most, first; Last Updated by is no owner
const FIRST = ["user_id", "invoice_user_id", "user_ids"];
const SKIPPED = ["write_uid"];

/**
 * The buttons "Salesperson = current user" of the rule form: Odoo's filter editor has no
 * current user to pick, these add the condition with uid, the user each filter is read for.
 * <widget name="om_current_user_domain" field="domain"/>
 */
export class CurrentUserDomain extends Component {
    static template = "om_access_manager.CurrentUserDomain";
    props = useProps({
        ...standardWidgetProps,
        record: t.object(),
        field: t.string().optional("domain"),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ fields: [] });
        onWillStart(() => this.load(this.props.record.data.model));
        onWillUpdateProps((next) => next.record.data.model !== this.props.record.data.model
            && this.load(next.record.data.model));
    }

    async load(modelName) {
        if (!modelName) {
            this.state.fields = [];
            return;
        }
        const fields = await this.orm.call(modelName, "fields_get", [], { attributes: ["string", "type", "relation", "store"] });
        const users = Object.entries(fields)
            .filter(([name, field]) => field.relation === "res.users" && field.store !== false
                && ["many2one", "many2many"].includes(field.type) && !SKIPPED.includes(name))
            .map(([name, field]) => ({ name, label: field.string, many: field.type === "many2many" }));
        const rank = (field) => (FIRST.includes(field.name) ? FIRST.indexOf(field.name)
            : field.name === "create_uid" ? 99 : 50);
        users.sort((a, b) => rank(a) - rank(b) || a.label.localeCompare(b.label));
        this.state.fields = users;
    }

    label(field) {
        return field.many ? _t("%s includes current user", field.label) : _t("%s = current user", field.label);
    }

    add(field) {
        const condition = field.many ? `[("${field.name}", "in", [uid])]` : `[("${field.name}", "=", uid)]`;
        const current = this.props.record.data[this.props.field] || "[]";
        const domain = Domain.and([current, condition]).toString();
        this.props.record.update({ [this.props.field]: domain });
    }
}

registry.category("view_widgets").add("om_current_user_domain", {
    component: CurrentUserDomain,
    extractProps: ({ attrs }) => ({ field: attrs.field || "domain" }),
});
