/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { ListRenderer } from "@web/views/list/list_renderer";

const PREFIX = "om_theme_lite.list_widths:";

/**
 * Column widths that stay where the user dragged them.
 *
 * Odoo forgets a resized column as soon as the list reloads. Here the widths are
 * saved in the browser per model and view when a drag ends, and handed back to
 * Odoo's own width calculation the next time the list opens, so the rest of its
 * layout logic keeps working.
 */
patch(ListRenderer.prototype, "om_theme_lite.list_widths", {
    onStartResize(ev) {
        this._super(...arguments);
        browser.addEventListener("mouseup", () => this.omSaveWidths(), { once: true });
    },

    omWidthsKey() {
        const viewId = this.env.config?.viewId || "default";
        return `${PREFIX}${this.props.list.resModel}:${viewId}`;
    },

    omSavedWidths() {
        try {
            return JSON.parse(browser.localStorage.getItem(this.omWidthsKey())) || {};
        } catch {
            return {};
        }
    },

    omSaveWidths() {
        const table = this.tableRef.el;
        if (!table) {
            return;
        }
        const widths = this.omSavedWidths();
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            widths[th.dataset.name] = Math.round(th.getBoundingClientRect().width);
        }
        browser.localStorage.setItem(this.omWidthsKey(), JSON.stringify(widths));
    },

    computeColumnWidthsFromContent() {
        const columnWidths = this._super(...arguments);
        const widths = this.omSavedWidths();
        if (!Object.keys(widths).length) {
            return columnWidths;
        }
        // the same header order Odoo measured in, so each width lands on its column
        const headers = [...this.tableRef.el.querySelectorAll("thead th")];
        headers.forEach((th, index) => {
            const width = widths[th.dataset.name];
            if (width) {
                th.style.maxWidth = null;
                columnWidths[index] = width;
            }
        });
        return columnWidths;
    },
});
