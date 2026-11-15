/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import ListRenderer from "web.ListRenderer";

const PREFIX = "om_theme_lite.list_widths:";

/**
 * Column widths that stay where the user dragged them.
 *
 * Odoo forgets a resized column as soon as the list reloads. Here the widths are
 * saved in the browser per model and set of columns when a drag ends, and handed
 * back to Odoo's own width calculation the next time the list opens, so the rest
 * of its layout logic keeps working.
 */
ListRenderer.include({
    _onStartResize(ev) {
        this._super(...arguments);
        if (this.isResizing) {
            browser.addEventListener("mouseup", () => this._omSaveWidths(), { once: true });
        }
    },

    /** The model and its columns: two list views of one model rarely share both. */
    _omWidthsKey() {
        const columns = (this.columns || []).map((column) => column.attrs.name).join(",");
        return `${PREFIX}${this.state.model}:${columns}`;
    },

    _omSavedWidths() {
        try {
            return JSON.parse(browser.localStorage.getItem(this._omWidthsKey())) || {};
        } catch {
            return {};
        }
    },

    _omSaveWidths() {
        const table = this.el && this.el.querySelector(".o_list_table");
        if (!table) {
            return;
        }
        const widths = this._omSavedWidths();
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            widths[th.dataset.name] = Math.round(th.getBoundingClientRect().width);
        }
        browser.localStorage.setItem(this._omWidthsKey(), JSON.stringify(widths));
    },

    _squeezeTable() {
        const columnWidths = this._super(...arguments);
        const widths = this._omSavedWidths();
        if (!Object.keys(widths).length) {
            return columnWidths;
        }
        // the same header order Odoo measured in, so each width lands on its column
        const headers = [...this.el.querySelectorAll(".o_list_table thead th")];
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
