import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

import { Component, signal, t, useProps } from "@odoo/owl";

/**
 * The fields folded away on this form, and the link that shows them again.
 *
 * The fields stay in the form - they are only out of sight - so nothing about the
 * record changes while they are folded.
 */
export class FadedToggle extends Component {
    static template = "om_adaptive_views.FadedToggle";
    props = useProps({
        ...standardWidgetProps,
        count: t.number().optional(0),
        tabs: t.number().optional(0),
        labels: t.string().optional(""),
    });

    open = signal(false);

    get label() {
        const { count, tabs } = this.props;
        if (this.open()) {
            return _t("Fold the rarely used ones again");
        }
        const fields = count === 1 ? _t("1 rarely used field") : _t("%(count)s rarely used fields", { count });
        const pages = tabs === 1 ? _t("1 rarely used tab") : _t("%(tabs)s rarely used tabs", { tabs });
        if (count && tabs) {
            return _t("Show %(fields)s and %(pages)s", { fields, pages });
        }
        return _t("Show %(what)s", { what: tabs ? pages : fields });
    }

    toggle(ev) {
        this.open.set(!this.open());
        ev.currentTarget.closest(".o_form_renderer")?.classList.toggle("o_om_show_faded", this.open());
    }
}

registry.category("view_widgets").add("om_faded_toggle", {
    component: FadedToggle,
    extractProps: ({ attrs }) => ({
        count: parseInt(attrs.count, 10) || 0,
        tabs: parseInt(attrs.tabs, 10) || 0,
        labels: attrs.labels || "",
    }),
});
