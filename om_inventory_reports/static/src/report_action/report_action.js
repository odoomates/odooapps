import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

import {
    ColumnsMenu,
    CompareMenu,
    DateFilter,
    ExportMenu,
    GroupByMenu,
    OptionsMenu,
    RecordFilter,
    ReportSwitcher,
    SavedViewsMenu,
} from "./report_filters";
import { formatValue, KpiCards, ReportTable } from "./report_table";

const ENGINE = "om.inventory.report";
const VIEW_MODEL = "om.inventory.report.view";

/**
 * What the reader left the report like, by action: going into a record and
 * back through the breadcrumb mounts the report again, and it reopens with
 * the same filters, unfolded lines and scroll.
 */
const savedStates = new WeakMap();

/**
 * The inventory reports, on screen: a report switcher and saved views at the
 * top, the filters under them, the key figures, then the report itself as a
 * table that unfolds group by group. Exports print what the screen shows.
 */
export class InventoryReport extends Component {
    static template = "om_inventory_reports.InventoryReport";
    static components = {
        ColumnsMenu,
        CompareMenu,
        ControlPanel,
        DateFilter,
        ExportMenu,
        GroupByMenu,
        KpiCards,
        OptionsMenu,
        RecordFilter,
        ReportSwitcher,
        ReportTable,
        SavedViewsMenu,
    };
    props = useProps(standardActionServiceProps);

    tableRef = signal.ref();
    searchRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.ui = useService("ui");
        this.state = proxy({
            catalog: [],
            report: null,
            reportKey: null,
            options: {},
            lines: [],
            more: 0,
            children: {},
            expanded: [],
            loading: true,
            reloading: false,
            error: null,
            views: [],
            viewId: false,
            density: localStorage.getItem("om_inventory_reports_density") || "comfortable",
            focusedId: null,
            exporting: false,
            overview: null,
        });
        this.searchValue = "";
        this.debouncedReload = useDebounced(() => this.reload(), 350);
        this.requestId = 0;
        onWillStart(() => this.start());
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    async start() {
        const saved = savedStates.get(this.props.action);
        const context = this.props.action.context || {};
        this.state.catalog = await this.orm.call(ENGINE, "om_get_catalog", []);
        if (saved) {
            Object.assign(this.state, {
                reportKey: saved.reportKey,
                options: saved.options,
                expanded: saved.expanded,
                viewId: saved.viewId,
            });
            this.scrollTop = saved.scrollTop;
            await this.loadViews();
        } else {
            this.state.reportKey = context.om_report || this.state.catalog[0]?.key;
            await this.loadViews();
            const defaultView = this.state.views.find((view) => view.is_default);
            if (context.om_options) {
                this.state.options = { ...context.om_options };
            } else if (defaultView) {
                this.state.options = { ...defaultView.options };
                this.state.viewId = defaultView.id;
            }
        }
        await this.reload({ keepExpanded: true });
    }

    get reportModel() {
        return this.state.catalog.find((r) => r.key === this.state.reportKey)?.model || ENGINE;
    }

    async loadViews() {
        this.state.views = await this.orm.call(VIEW_MODEL, "om_list", [this.state.reportKey]);
    }

    get isOverview() {
        return this.state.reportKey === "overview";
    }

    async reload({ keepExpanded = false } = {}) {
        if (this.isOverview) {
            this.state.report = null;
            this.state.overview = await this.orm.call(ENGINE, "om_get_overview", []);
            this.state.loading = false;
            this.env.config?.setDisplayName?.(_t("Inventory Overview"));
            this.saveState();
            return;
        }
        const requestId = ++this.requestId;
        this.state.reloading = !this.state.loading;
        this.state.error = null;
        const expanded = keepExpanded ? this.state.expanded : [];
        try {
            const report = await this.orm.call(this.reportModel, "om_get_report", [this.state.options], {
                expanded,
            });
            if (requestId !== this.requestId) {
                return;
            }
            this.state.report = report;
            this.state.options = report.options;
            this.state.lines = report.lines;
            this.state.more = report.more;
            this.state.children = Object.fromEntries(
                Object.entries(report.children).map(([id, c]) => [id, { ...c, loading: false }])
            );
            this.state.expanded = expanded.filter((id) => id in report.children);
            if (!keepExpanded && report.lines.length && this.expandByDefault(report)) {
                await this.expandAll();
            }
            this.env.config?.setDisplayName?.(report.name);
            this.saveState();
        } catch (error) {
            if (requestId === this.requestId) {
                this.state.error = error.data?.message || error.message || _t("The report could not be loaded.");
            }
            throw error;
        } finally {
            if (requestId === this.requestId) {
                this.state.loading = false;
                this.state.reloading = false;
            }
        }
        if (this.scrollTop) {
            const top = this.scrollTop;
            this.scrollTop = 0;
            requestAnimationFrame(() => {
                const el = this.tableRef();
                if (el) {
                    el.scrollTop = top;
                }
            });
        }
    }

    expandByDefault(report) {
        return report.key === "negative" && report.lines.length <= 20;
    }

    saveState() {
        savedStates.set(this.props.action, {
            reportKey: this.state.reportKey,
            options: this.state.options,
            expanded: this.state.expanded,
            viewId: this.state.viewId,
            scrollTop: this.tableRef()?.scrollTop || 0,
        });
    }

    // ------------------------------------------------------------------
    // Options
    // ------------------------------------------------------------------

    /** Change options and reload; `debounce` for typing. */
    setOptions(patch, { debounce = false, keepExpanded = false } = {}) {
        Object.assign(this.state.options, patch);
        this.state.viewId = false;
        if (debounce) {
            this.debouncedReload();
        } else {
            this.reload({ keepExpanded });
        }
    }

    setFilter(filter, ids) {
        this.setOptions({ [filter.option]: ids });
    }

    get visibleColumns() {
        return (this.state.report?.columns || []).filter((column) => column.visible);
    }

    get groupLabel() {
        const dims = this.state.report?.group_by || [];
        return (this.state.options.group_by || [])
            .map((key) => dims.find((d) => d.key === key)?.label)
            .filter(Boolean)
            .join(" / ");
    }

    onSearchInput(ev) {
        this.setOptions({ search: ev.target.value }, { debounce: true });
    }

    clearFilters() {
        const keep = { group_by: this.state.options.group_by, columns: this.state.options.columns };
        this.state.options = keep;
        this.state.viewId = false;
        this.reload();
    }

    get activeFilterCount() {
        const options = this.state.options;
        const filterKeys = (this.state.report?.filters || []).map((f) => f.option);
        return filterKeys.filter((key) => options[key]?.length).length + (options.search ? 1 : 0);
    }

    get chips() {
        const report = this.state.report;
        if (!report) {
            return [];
        }
        const chips = [];
        if (this.state.options.kpi_filter) {
            const kpi = report.kpis.find((k) => k.filter === this.state.options.kpi_filter);
            chips.push({
                key: "kpi",
                label: kpi ? kpi.label : this.state.options.kpi_filter,
                icon: "filter_alt",
                remove: () => this.setOptions({ kpi_filter: false }),
            });
        }
        if (this.state.options.search) {
            chips.push({
                key: "search",
                label: `"${this.state.options.search}"`,
                icon: "search",
                remove: () => this.setOptions({ search: "" }),
            });
        }
        return chips;
    }

    toggleKpi(kpi) {
        if (!kpi.filter) {
            return;
        }
        const active = this.state.options.kpi_filter === kpi.filter;
        this.setOptions({ kpi_filter: active ? false : kpi.filter });
    }

    setDensity(density) {
        this.state.density = density;
        localStorage.setItem("om_inventory_reports_density", density);
    }

    sortBy(column) {
        const sort = this.state.options.sort || {};
        let next;
        if (sort.key !== column.key) {
            next = { key: column.key, dir: column.type === "char" ? "asc" : "desc" };
        } else if (sort.dir === "desc") {
            next = { key: column.key, dir: "asc" };
        } else {
            next = false;
        }
        this.setOptions({ sort: next }, { keepExpanded: true });
    }

    // ------------------------------------------------------------------
    // Reports and views
    // ------------------------------------------------------------------

    async switchReport(key, options = null) {
        if (key === this.state.reportKey && !options) {
            return;
        }
        const previous = this.state.options;
        // what both reports understand is carried over
        const carried = {};
        for (const k of ["warehouse_ids", "location_ids", "product_ids", "category_ids", "lot_ids"]) {
            if (previous[k]?.length) {
                carried[k] = previous[k];
            }
        }
        const target = this.state.report?.date_mode;
        if (target && target !== "none" && previous.date_preset) {
            Object.assign(carried, {
                date_preset: previous.date_preset,
                date_from: previous.date_from,
                date_to: previous.date_to,
            });
        }
        this.state.reportKey = key;
        this.state.report = null;
        this.state.overview = null;
        this.state.lines = [];
        this.state.expanded = [];
        this.state.children = {};
        this.state.viewId = false;
        this.state.loading = true;
        this.state.options = options ? { ...options } : carried;
        await this.loadViews();
        if (!options) {
            const defaultView = this.state.views.find((view) => view.is_default);
            if (defaultView) {
                this.state.options = { ...carried, ...defaultView.options };
                this.state.viewId = defaultView.id;
            }
        }
        await this.reload();
    }

    formatKpi(kpi) {
        const overview = this.state.overview;
        return (
            formatValue(kpi.value, kpi.type, { digits: overview.digits, currencyId: overview.currency_id }) || "0"
        );
    }

    openFromOverview(card, kpi = null) {
        this.switchReport(card.key, kpi?.filter ? { kpi_filter: kpi.filter } : null);
    }

    applyView(view) {
        this.state.options = { ...view.options };
        this.state.viewId = view.id;
        this.state.expanded = [];
        this.reload().then(() => (this.state.viewId = view.id));
    }

    async saveView({ name, shared, isDefault, overwrite }) {
        const viewId = await this.orm.call(VIEW_MODEL, "om_save", [
            this.state.reportKey,
            name,
            this.state.options,
        ], { shared, is_default: isDefault, view_id: overwrite ? this.state.viewId : false });
        await this.loadViews();
        this.state.viewId = viewId;
        this.notification.add(_t("View \"%s\" saved.", name), { type: "success" });
    }

    async scheduleView(view) {
        this.saveState();
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Scheduled Report"),
            res_model: "om.inventory.report.schedule",
            views: [[false, "form"]],
            target: "current",
            context: { default_view_id: view.id, default_name: view.name },
        });
    }

    async deleteView(view) {
        await this.orm.call(VIEW_MODEL, "om_delete", [[view.id]]);
        if (this.state.viewId === view.id) {
            this.state.viewId = false;
        }
        await this.loadViews();
    }

    // ------------------------------------------------------------------
    // Lines
    // ------------------------------------------------------------------

    isExpanded(line) {
        return this.state.expanded.includes(line.id);
    }

    async toggleLine(line) {
        if (!line.has_children) {
            return;
        }
        if (this.isExpanded(line)) {
            this.state.expanded = this.state.expanded.filter(
                (id) => id !== line.id && !id.startsWith(line.id + "|")
            );
        } else {
            this.state.expanded = [...this.state.expanded, line.id];
            if (!this.state.children[line.id]) {
                await this.loadChildren(line.id);
            }
        }
        this.saveState();
    }

    async loadChildren(lineId, offset = 0) {
        const existing = this.state.children[lineId];
        this.state.children[lineId] = { lines: existing?.lines || [], more: 0, loading: true };
        const result = await this.orm.call(this.reportModel, "om_get_children", [
            this.state.options,
            lineId,
        ], { offset });
        this.state.children[lineId] = {
            lines: offset ? [...(existing?.lines || []), ...result.lines] : result.lines,
            more: result.more,
            loading: false,
        };
    }

    async loadMore(parentId) {
        if (!parentId) {
            const result = await this.orm.call(this.reportModel, "om_get_children", [
                this.state.options,
                "",
            ], { offset: this.state.lines.length });
            this.state.lines = [...this.state.lines, ...result.lines];
            this.state.more = result.more;
            return;
        }
        await this.loadChildren(parentId, this.state.children[parentId].lines.length);
    }

    async expandAll() {
        // unfold group by group, level by level, up to the leaves' details
        let frontier = this.state.lines.filter((l) => l.has_children && l.kind === "group");
        let guard = 0;
        while (frontier.length && guard++ < 6) {
            const next = [];
            await Promise.all(
                frontier.map(async (line) => {
                    if (!this.state.expanded.includes(line.id)) {
                        this.state.expanded.push(line.id);
                    }
                    if (!this.state.children[line.id]) {
                        await this.loadChildren(line.id);
                    }
                    next.push(
                        ...this.state.children[line.id].lines.filter(
                            (l) => l.has_children && l.kind === "group"
                        )
                    );
                })
            );
            frontier = next;
        }
        this.saveState();
    }

    collapseAll() {
        this.state.expanded = [];
        this.saveState();
    }

    /** The rows as drawn: lines, with the children of unfolded lines under them. */
    get rows() {
        const rows = [];
        const walk = (lines, parentId, more) => {
            for (const line of lines) {
                rows.push(line);
                if (this.state.expanded.includes(line.id)) {
                    const children = this.state.children[line.id];
                    if (!children || (children.loading && !children.lines.length)) {
                        rows.push({ id: `${line.id}|loading`, kind: "loading", level: line.level + 1 });
                    } else {
                        walk(children.lines, line.id, children.more);
                    }
                }
            }
            if (more) {
                const level = lines[0]?.level ?? 0;
                rows.push({
                    id: `${parentId || "root"}|more`,
                    kind: "more",
                    level,
                    parentId,
                    more,
                    next: Math.min(more, 200),
                });
            }
        };
        walk(this.state.lines, false, this.state.more);
        return rows;
    }

    async openLine(line) {
        if (!line.open) {
            if (line.has_children) {
                await this.toggleLine(line);
            }
            return;
        }
        this.saveState();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: line.open.res_model,
            res_id: line.open.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async followLink(link) {
        this.saveState();
        const report = this.state.catalog.find((r) => r.key === link.report);
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "om_inventory_report",
            name: report?.name || link.label,
            context: { om_report: link.report, om_options: link.options },
        });
    }

    /** Arrows move between rows, right/left unfold and fold, Enter opens. */
    onKeydown(ev) {
        if (ev.target.closest("input, .dropdown-menu")) {
            return;
        }
        if (ev.key === "/") {
            ev.preventDefault();
            this.searchRef()?.focus();
            return;
        }
        const rows = this.rows.filter((r) => !["loading", "more"].includes(r.kind));
        const index = rows.findIndex((r) => r.id === this.state.focusedId);
        const row = rows[index];
        switch (ev.key) {
            case "ArrowDown":
            case "ArrowUp": {
                ev.preventDefault();
                const next = rows[Math.max(0, Math.min(rows.length - 1, index + (ev.key === "ArrowDown" ? 1 : -1)))];
                if (next) {
                    this.state.focusedId = next.id;
                    this.tableRef()
                        ?.querySelector(`tr[data-id="${CSS.escape(next.id)}"]`)
                        ?.scrollIntoView({ block: "nearest" });
                }
                break;
            }
            case "ArrowRight":
            case "+":
                if (row?.has_children && !this.isExpanded(row)) {
                    ev.preventDefault();
                    this.toggleLine(row);
                }
                break;
            case "ArrowLeft":
            case "-":
                if (row && this.isExpanded(row)) {
                    ev.preventDefault();
                    this.toggleLine(row);
                } else if (row?.parent_id) {
                    ev.preventDefault();
                    this.state.focusedId = row.parent_id;
                }
                break;
            case "Enter":
                if (row) {
                    ev.preventDefault();
                    if (row.has_children) {
                        this.toggleLine(row);
                    } else {
                        this.openLine(row);
                    }
                }
                break;
        }
    }

    onTableScroll() {
        this.saveStateDebounced ||= this.debounce(() => this.saveState(), 200);
        this.saveStateDebounced();
    }

    debounce(fn, delay) {
        let timer;
        return () => {
            clearTimeout(timer);
            timer = setTimeout(fn, delay);
        };
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------

    async export(format, expandAll = false) {
        this.state.exporting = format;
        try {
            await download({
                url: "/om_inventory_reports/export",
                data: {
                    data: JSON.stringify({
                        report: this.state.reportKey,
                        format,
                        options: this.state.options,
                        expanded: this.state.expanded,
                        expand_all: expandAll,
                    }),
                },
            });
        } finally {
            this.state.exporting = false;
        }
    }
}

registry.category("actions").add("om_inventory_report", InventoryReport);
