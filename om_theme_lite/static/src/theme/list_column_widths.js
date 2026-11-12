import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { ListRenderer } from "@web/views/list/list_renderer";

const PREFIX = "om_theme_lite.list_widths:";

/**
 * Column widths that stay where the user dragged them.
 *
 * Odoo forgets a resized column as soon as the list reloads. Here the widths are
 * saved in the browser per model and view when a drag ends, and handed back to
 * Odoo's own width calculation as fixed widths the next time the list opens, so
 * the rest of its layout logic keeps working. Double-clicking a column edge clears
 * them, as it already resets the widths in Odoo.
 */
patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        const hook = this.columnWidths;
        this.columnWidths = {
            get resizing() {
                return hook.resizing;
            },
            onStartResize: (ev) => {
                hook.onStartResize(ev);
                browser.addEventListener("pointerup", () => this.omSaveWidths(), { once: true });
            },
            resetWidths: (...args) => {
                this.omClearWidths();
                this.columns = this.getActiveColumns();
                return hook.resetWidths(...args);
            },
        };
    },

    get omWidthsKey() {
        const viewId = this.env.config?.viewId || "default";
        return `${PREFIX}${this.props.list.resModel}:${viewId}`;
    },

    omSavedWidths() {
        try {
            return JSON.parse(browser.localStorage.getItem(this.omWidthsKey)) || {};
        } catch {
            return {};
        }
    },

    omSaveWidths() {
        const table = this.tableRef();
        if (!table) {
            return;
        }
        const widths = this.omSavedWidths();
        for (const th of table.querySelectorAll("thead th[data-name]")) {
            // without the cell padding, which Odoo adds back on its own
            const { paddingLeft, paddingRight } = getComputedStyle(th);
            const padding = parseFloat(paddingLeft) + parseFloat(paddingRight);
            widths[th.dataset.name] = Math.round(th.getBoundingClientRect().width - padding);
        }
        browser.localStorage.setItem(this.omWidthsKey, JSON.stringify(widths));
    },

    omClearWidths() {
        browser.localStorage.removeItem(this.omWidthsKey);
    },

    getActiveColumns() {
        const columns = super.getActiveColumns(...arguments);
        const widths = this.omSavedWidths();
        if (!Object.keys(widths).length) {
            return columns;
        }
        // a copy with a width attribute, so the arch the view was built from is
        // left untouched
        return columns.map((column) =>
            widths[column.name]
                ? { ...column, attrs: { ...column.attrs, width: `${widths[column.name]}px` } }
                : column
        );
    },
});
