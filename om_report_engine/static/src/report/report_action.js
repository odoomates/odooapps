import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

import {
    ChoiceMenu,
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
import { formatValue } from "./format";
import { NoteDialog } from "./note_dialog";
import { chartFilterLabel, KpiCards, ReportChart } from "./report_insights";
import { ReportTable } from "./report_table";

const ENGINE = "om.report";
const VIEW_MODEL = "om.report.view";
const FOLD_MODEL = "om.report.fold";
const SCHEDULE_MODEL = "om.report.schedule";
// the catalog entry of the overview of an app (see om.report.om_get_overview)
const OVERVIEW = "overview";

/**
 * What the reader left the report like, by action: going into a record and
 * back through the breadcrumb mounts the report again, and it reopens with
 * the same filters, unfolded lines and scroll.
 */
const savedStates = new WeakMap();

/**
 * A dynamic report on screen. Everything it draws comes from the report model
 * (see om.report): the filters, the options, the columns and the lines. The
 * action says which report with `om_report_model` in its context, and which
 * reports share the switcher with `om_report_app`; `om_report_model: "overview"`
 * opens the overview of the app, a card per report with its key figures.
 */
export class OmReport extends Component {
    static template = "om_report_engine.Report";
    static components = {
        ChoiceMenu,
        ColumnsMenu,
        CompareMenu,
        ControlPanel,
        DateFilter,
        ExportMenu,
        GroupByMenu,
        KpiCards,
        OptionsMenu,
        RecordFilter,
        ReportChart,
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
        this.dialog = useService("dialog");
        this.state = proxy({
            catalog: [],
            reportModel: null,
            report: null,
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
            density: localStorage.getItem("om_report_engine_density") || "comfortable",
            focusedId: false,
            exporting: false,
            overview: null,
        });
        this.debouncedReload = useDebounced(() => this.reload({ keepExpanded: true }), 350);
        // the folds are remembered for the user once they stop clicking
        this.debouncedRememberFolds = useDebounced(() => this.rememberFolds(), 800);
        this.requestId = 0;
        onWillStart(() => this.start());
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    get context() {
        return this.props.action.context || {};
    }

    async start() {
        const saved = savedStates.get(this.props.action);
        const app = this.context.om_report_app || false;
        this.state.catalog = app ? await this.orm.call(ENGINE, "om_get_catalog", [app]) : [];
        if (saved) {
            Object.assign(this.state, {
                reportModel: saved.reportModel,
                options: saved.options,
                expanded: saved.expanded,
                viewId: saved.viewId,
            });
            this.scrollTop = saved.scrollTop;
            await this.loadViews();
        } else {
            this.state.reportModel = this.context.om_report_model || this.state.catalog[0]?.model;
            await this.loadViews();
            await this.loadFolds();
            const defaultView = this.state.views.find((view) => view.is_default);
            if (this.context.om_options) {
                this.state.options = { ...this.context.om_options };
            } else if (defaultView) {
                this.state.options = { ...defaultView.options };
                this.state.viewId = defaultView.id;
            }
        }
        await this.reload({ keepExpanded: true, autoUnfold: !saved && !this.foldsRemembered });
    }

    get isOverview() {
        return this.state.reportModel === OVERVIEW;
    }

    /** The lines the user left unfolded the last time, if any. */
    async loadFolds() {
        if (this.isOverview) {
            this.foldsRemembered = true;
            return;
        }
        const expanded = await this.orm.call(FOLD_MODEL, "om_get", [this.state.reportModel]);
        this.foldsRemembered = Array.isArray(expanded);
        if (this.foldsRemembered) {
            this.state.expanded = expanded;
        }
    }

    rememberFolds() {
        this.foldsRemembered = true;
        return this.orm.call(FOLD_MODEL, "om_set", [this.state.reportModel, this.state.expanded]);
    }

    async loadViews() {
        this.state.views = this.isOverview
            ? []
            : await this.orm.call(VIEW_MODEL, "om_list", [this.state.reportModel]);
    }

    async reload({ keepExpanded = false, autoUnfold = false } = {}) {
        const requestId = ++this.requestId;
        if (this.isOverview) {
            this.state.report = null;
            const overview = await this.orm.call(ENGINE, "om_get_overview", [this.context.om_report_app]);
            if (requestId === this.requestId) {
                this.state.overview = overview;
                this.state.loading = false;
                this.state.reloading = false;
                this.env.config?.setDisplayName?.(this.props.action.name || _t("Overview"));
                this.saveState();
            }
            return;
        }
        this.state.reloading = !this.state.loading;
        this.state.error = null;
        const expanded = keepExpanded ? this.state.expanded : [];
        try {
            const report = await this.orm.call(this.state.reportModel, "om_get_report", [this.state.options], {
                expanded,
                auto_unfold: autoUnfold || !keepExpanded,
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
            this.state.expanded = report.expanded;
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

    saveState() {
        savedStates.set(this.props.action, {
            reportModel: this.state.reportModel,
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
    setOptions(patch, { debounce = false, keepExpanded = true } = {}) {
        Object.assign(this.state.options, patch);
        this.state.viewId = false;
        if (debounce) {
            this.debouncedReload();
        } else {
            this.reload({ keepExpanded });
        }
    }

    get visibleColumns() {
        return (this.state.report?.columns || []).filter((column) => column.visible);
    }

    get barChoices() {
        return (this.state.report?.choices || []).filter((choice) => choice.menu === "bar");
    }

    get menuChoices() {
        return (this.state.report?.choices || []).filter((choice) => choice.menu !== "bar");
    }

    onSearchInput(ev) {
        this.setOptions({ search: ev.target.value }, { debounce: true });
    }

    clearFilters() {
        const options = { ...this.state.options };
        for (const filter of this.state.report?.filters || []) {
            options[filter.key] = [];
        }
        options.search = "";
        options.kpi_filter = false;
        this.state.options = options;
        this.state.viewId = false;
        this.reload();
    }

    get activeFilterCount() {
        const options = this.state.options;
        const keys = (this.state.report?.filters || []).map((f) => f.key);
        return keys.filter((key) => options[key]?.length).length + (options.search ? 1 : 0);
    }

    /** The filters set by a key figure, a chart and the search, each removable. */
    get chips() {
        const report = this.state.report;
        if (!report) {
            return [];
        }
        const chips = [];
        const kpiFilter = this.state.options.kpi_filter;
        if (kpiFilter) {
            const kpi = (report.kpis || []).find((k) => k.filter === kpiFilter);
            chips.push({
                key: "kpi",
                label: kpi ? kpi.label : chartFilterLabel(report.chart, kpiFilter) || kpiFilter,
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

    /** A key figure, chart bar or matrix cell narrows the report down; clicked again, it no longer does. */
    toggleKpi(kpi) {
        if (!kpi.filter) {
            return;
        }
        const active = this.state.options.kpi_filter === kpi.filter;
        this.setOptions({ kpi_filter: active ? false : kpi.filter });
    }

    formatKpi(card, kpi) {
        return (
            formatValue(kpi.value, kpi.type, {
                digits: kpi.type === "float" ? card.digits : undefined,
                currencyId: card.currency_id,
            }) || "0"
        );
    }

    openFromOverview(card, kpi = null) {
        this.switchReport(card.model, kpi?.filter ? { kpi_filter: kpi.filter } : null);
    }

    setDensity(density) {
        this.state.density = density;
        localStorage.setItem("om_report_engine_density", density);
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
        this.setOptions({ sort: next });
    }

    // ------------------------------------------------------------------
    // Reports and views
    // ------------------------------------------------------------------

    async switchReport(model, options = null) {
        if (model === this.state.reportModel && !options) {
            return;
        }
        // what both reports understand is carried over: the period and the records filtered on
        const previous = this.state.options;
        const carried = {};
        for (const filter of this.state.report?.filters || []) {
            if (previous[filter.key]?.length) {
                carried[filter.key] = previous[filter.key];
            }
        }
        if (previous.date_preset) {
            Object.assign(carried, {
                date_preset: previous.date_preset,
                date_from: previous.date_from,
                date_to: previous.date_to,
            });
        }
        Object.assign(this.state, {
            reportModel: model,
            report: null,
            overview: null,
            lines: [],
            expanded: [],
            children: {},
            viewId: false,
            loading: true,
            options: options ? { ...options } : carried,
        });
        await this.loadViews();
        await this.loadFolds();
        if (!options) {
            const defaultView = this.state.views.find((view) => view.is_default);
            if (defaultView) {
                this.state.options = { ...carried, ...defaultView.options };
                this.state.viewId = defaultView.id;
            }
        }
        await this.reload({ keepExpanded: this.foldsRemembered, autoUnfold: !this.foldsRemembered });
    }

    applyView(view) {
        this.state.options = { ...view.options };
        this.state.expanded = [];
        this.reload().then(() => (this.state.viewId = view.id));
    }

    async saveView({ name, shared, isDefault, overwrite }) {
        const viewId = await this.orm.call(VIEW_MODEL, "om_save", [this.state.reportModel, name, this.state.options], {
            shared,
            is_default: isDefault,
            view_id: overwrite ? this.state.viewId : false,
        });
        await this.loadViews();
        this.state.viewId = viewId;
        this.notification.add(_t('View "%s" saved.', name), { type: "success" });
    }

    /** The form of a scheduled report sending the view by email. */
    async scheduleView(view) {
        this.saveState();
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Scheduled Report"),
            res_model: SCHEDULE_MODEL,
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
            this.state.expanded = this.state.expanded.filter((id) => id !== line.id && !id.startsWith(line.id + "|"));
        } else {
            this.state.expanded = [...this.state.expanded, line.id];
            if (!this.state.children[line.id]) {
                await this.loadChildren(line.id);
            }
        }
        this.saveState();
        this.debouncedRememberFolds();
    }

    async loadChildren(lineId, offset = 0) {
        const existing = this.state.children[lineId];
        this.state.children[lineId] = { lines: existing?.lines || [], more: 0, loading: true };
        const result = await this.orm.call(this.state.reportModel, "om_get_children", [this.state.options, lineId], {
            offset,
        });
        this.state.children[lineId] = {
            lines: offset ? [...(existing?.lines || []), ...result.lines] : result.lines,
            more: result.more,
            loading: false,
        };
    }

    async loadMore(parentId) {
        if (!parentId) {
            const result = await this.orm.call(this.state.reportModel, "om_get_children", [this.state.options, ""], {
                offset: this.state.lines.length,
            });
            this.state.lines = [...this.state.lines, ...result.lines];
            this.state.more = result.more;
            return;
        }
        await this.loadChildren(parentId, this.state.children[parentId].lines.length);
    }

    /** Unfold everything that has children, level by level (details included). */
    async expandAll() {
        let frontier = this.state.lines.filter((l) => l.has_children);
        let guard = 0;
        while (frontier.length && guard++ < 8) {
            const next = [];
            await Promise.all(
                frontier.map(async (line) => {
                    if (!this.state.expanded.includes(line.id)) {
                        this.state.expanded.push(line.id);
                    }
                    if (!this.state.children[line.id]) {
                        await this.loadChildren(line.id);
                    }
                    next.push(...this.state.children[line.id].lines.filter((l) => l.has_children));
                })
            );
            frontier = next;
        }
        this.saveState();
        this.debouncedRememberFolds();
    }

    collapseAll() {
        this.state.expanded = [];
        this.saveState();
        this.debouncedRememberFolds();
    }

    /** The rows as drawn: lines, with the children of unfolded lines under them. */
    get rows() {
        const rows = [];
        const pageSize = this.state.report?.page_size || 200;
        const walk = (lines, parentId, more, level) => {
            for (const line of lines) {
                rows.push(line);
                if (this.state.expanded.includes(line.id)) {
                    const children = this.state.children[line.id];
                    if (!children || (children.loading && !children.lines.length)) {
                        rows.push({ id: `${line.id}|loading`, kind: "loading", level: line.level + 1 });
                    } else {
                        walk(children.lines, line.id, children.more, line.level + 1);
                    }
                }
            }
            if (more) {
                rows.push({
                    id: `${parentId || "root"}|more`,
                    kind: "more",
                    level,
                    parentId,
                    more,
                    next: Math.min(more, pageSize),
                });
            }
        };
        walk(this.state.lines, false, this.state.more, 0);
        return rows;
    }

    async openLine(line) {
        this.saveState();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: line.open.res_model,
            res_id: line.open.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async drillLine(line) {
        const action = await this.orm.call(this.state.reportModel, "om_open_line", [this.state.options, line.id]);
        if (action) {
            this.saveState();
            await this.action.doAction(action);
        }
    }

    async drillCell(line, column) {
        const action = await this.orm.call(this.state.reportModel, "om_open_cell", [
            this.state.options,
            line.id,
            column.key,
        ]);
        if (action) {
            this.saveState();
            await this.action.doAction(action);
        }
    }

    /** The notes of a figure, in a dialog; the line shows them as soon as they change. */
    async openNotes(line, column) {
        const model = this.state.reportModel;
        const notes = await this.orm.call(model, "om_get_notes", [this.state.options, line.id, column.key]);
        const refresh = (result) => {
            line.notes = { ...(line.notes || {}), [column.key]: result };
            return result;
        };
        this.dialog.add(NoteDialog, {
            title: line.name,
            subtitle: column.group ? `${column.group} · ${column.label}` : column.label,
            notes,
            onSave: async (text, noteId) =>
                refresh(
                    await this.orm.call(model, "om_save_note", [this.state.options, line.id, column.key, text], {
                        note_id: noteId || false,
                    })
                ),
            onDelete: async (noteId) => {
                await this.orm.call(model, "om_delete_note", [noteId]);
                return refresh(await this.orm.call(model, "om_get_notes", [this.state.options, line.id, column.key]));
            },
        });
    }

    async lineButton(line, button) {
        const action = await this.orm.call(this.state.reportModel, "om_line_button", [
            this.state.options,
            line.id,
            button.key,
        ]);
        if (action) {
            this.saveState();
            await this.action.doAction(action);
        }
    }

    async followLink(link) {
        this.saveState();
        const report = this.state.catalog.find((r) => r.model === link.model);
        const options = { ...link.options };
        if (!("date_preset" in options) && this.state.options.date_preset) {
            Object.assign(options, {
                date_preset: this.state.options.date_preset,
                date_from: this.state.options.date_from,
                date_to: this.state.options.date_to,
            });
        }
        await this.action.doAction({
            type: "ir.actions.client",
            tag: "om_report",
            name: report?.name || link.label,
            context: { om_report_model: link.model, om_report_app: this.context.om_report_app, om_options: options },
        });
    }

    /** Arrows move between rows, right/left unfold and fold, Enter opens, "/" searches. */
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
                const step = ev.key === "ArrowDown" ? 1 : -1;
                const next = rows[Math.max(0, Math.min(rows.length - 1, index + step))];
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
                    } else if (row.open) {
                        this.openLine(row);
                    } else if (row.drill) {
                        this.drillLine(row);
                    }
                }
                break;
        }
    }

    onTableScroll() {
        clearTimeout(this.scrollTimer);
        this.scrollTimer = setTimeout(() => this.saveState(), 200);
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------

    async export(format, expandAll = false) {
        this.state.exporting = format;
        try {
            await download({
                url: "/om_report_engine/export",
                data: {
                    data: JSON.stringify({
                        model: this.state.reportModel,
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

registry.category("actions").add("om_report", OmReport);
