import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";

/**
 * A refresh button beside the pager.
 *
 * It reloads what the view shows - the records of a list or a kanban, the figures
 * of a pivot or a graph - with the same filters, without reloading the page. Views
 * without a search, such as a single record, have nothing to refresh this way and
 * get no button.
 */
patch(ControlPanel.prototype, {
    get omCanRefresh() {
        return Boolean(this.env.searchModel) && this.env.config?.viewType !== "form";
    },

    omRefresh() {
        this.env.searchModel.search();
    },
});
