/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import LegacyControlPanel from "web.ControlPanel";

/**
 * A refresh button beside the pager.
 *
 * It reloads what the view shows - the records of a list or a kanban, the figures
 * of a pivot or a graph - with the same filters, without reloading the page. Views
 * without a search, such as a single record, have nothing to refresh this way and
 * get no button.
 */
patch(ControlPanel.prototype, "om_theme_lite.refresh", {
    omCanRefresh() {
        return Boolean(this.env.searchModel) && this.env.config.viewType !== "form";
    },

    omRefresh() {
        this.env.searchModel.search();
    },
});

/** The same for the older views: list, kanban, form and the rest. */
patch(LegacyControlPanel.prototype, "om_theme_lite.refresh", {
    omCanRefresh() {
        return Boolean(this.model) && Boolean(this.props.view) && this.props.view.type !== "form";
    },

    omRefresh() {
        this.model.trigger("search", this.model.get("query"));
    },
});
