import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { formatFloat, formatInteger, formatMonetary } from "@web/views/fields/formatters";

/** A value of the report, formatted for its column type. */
export function formatValue(value, type, { digits = 2, currencyId = false } = {}) {
    if (value === undefined || value === null || value === false || value === "") {
        return "";
    }
    switch (type) {
        case "float":
            return formatFloat(value, { digits: [16, digits] });
        case "monetary":
            return formatMonetary(value, { currencyId, digits: [16, 2] });
        case "int":
            return formatInteger(value);
        case "percent":
            return `${formatFloat(value, { digits: [16, 1] })} %`;
        case "ratio":
            return formatFloat(value, { digits: [16, 2] });
        case "days":
            return _t("%s d", formatInteger(Math.round(value)));
        case "datetime":
            return formatDateTime(deserializeDateTime(value), {
                format: localization.dateTimeFormat.replace(/:ss/, ""),
            });
        case "date":
            return formatDate(deserializeDate(value));
        default:
            return String(value);
    }
}

const NUMERIC = ["float", "monetary", "int", "percent", "days", "ratio"];

/** The label of a chart bar, slice or cell, for the chip of the filter it set. */
export function chartFilterLabel(chart, filter) {
    if (!chart || !filter) {
        return "";
    }
    if (chart.type === "matrix") {
        for (const row of chart.rows) {
            for (const col of chart.cols) {
                const cell = chart.cells[row.key]?.[col.key];
                if (cell?.filter === filter) {
                    return `${row.label} · ${col.label}`;
                }
            }
        }
        return "";
    }
    return chart.items.find((item) => item.filter === filter)?.label || "";
}

/**
 * The chart above the table: horizontal bars, a donut, or a matrix of two
 * classifications. A bar, a slice or a cell with a filter narrows the report
 * down, like a key figure.
 */
export class ReportChart extends Component {
    static template = "om_inventory_reports.ReportChart";
    props = useProps({
        chart: t.object(),
        report: t.object(),
        active: t.or([t.string(), t.boolean()]).optional(),
        onSelect: t.function(),
    });

    format(value, type) {
        return formatValue(value, type || this.props.chart.value_type, {
            digits: this.props.report.digits,
            currencyId: this.props.report.currency_id,
        }) || "0";
    }

    get items() {
        return this.props.chart.items || [];
    }

    get total() {
        return this.items.reduce((sum, item) => sum + Math.max(item.value || 0, 0), 0);
    }

    /** Bars are drawn against the largest value; a negative cover counts as none. */
    barWidth(item) {
        const max = Math.max(...this.items.map((i) => Math.max(i.value || 0, 0)), 0);
        if (!max || item.value <= 0) {
            return "0%";
        }
        return `${Math.max((item.value / max) * 100, 1.5)}%`;
    }

    share(item) {
        return this.total ? (Math.max(item.value || 0, 0) / this.total) * 100 : 0;
    }

    /**
     * The donut's slices, as dashes of one circle whose length is 100: each
     * slice is its share long and starts where the previous one ended, from
     * the top.
     */
    get slices() {
        let start = 0;
        return this.items
            .filter((item) => item.value > 0)
            .map((item) => {
                const share = this.share(item);
                const slice = { item, dash: `${share} ${100 - share}`, offset: 25 - start };
                start += share;
                return slice;
            });
    }

    cell(row, col) {
        return this.props.chart.cells[row.key]?.[col.key] || { value: 0 };
    }

    /** Cells shaded by how many products they hold, against the fullest one. */
    cellStyle(row, col) {
        const cells = Object.values(this.props.chart.cells).flatMap((r) => Object.values(r));
        const max = Math.max(...cells.map((c) => c.value || 0), 0);
        const value = this.cell(row, col).value || 0;
        const strength = max ? 0.06 + (value / max) * 0.3 : 0;
        return `--om-cell-strength: ${strength.toFixed(3)}`;
    }

    itemClass(item) {
        const classes = [`o_om_tone_${item.tone || "neutral"}`];
        if (item.filter) {
            classes.push("o_om_chart_filter");
            if (item.filter === this.props.active) {
                classes.push("o_om_chart_active");
            }
        }
        return classes.join(" ");
    }

    select(item) {
        if (item.filter) {
            this.props.onSelect(item);
        }
    }
}

/** The key figures above the table; those with a filter narrow the report down. */
export class KpiCards extends Component {
    static template = "om_inventory_reports.KpiCards";
    props = useProps({
        kpis: t.array(),
        active: t.or([t.string(), t.boolean()]).optional(),
        report: t.object(),
        onSelect: t.function(),
    });

    kpiClass(kpi) {
        const classes = [`o_om_tone_${kpi.tone || "neutral"}`];
        if (kpi.filter) {
            classes.push("o_om_kpi_filter");
            if (kpi.filter === this.props.active) {
                classes.push("o_om_kpi_active");
            }
        }
        return classes.join(" ");
    }

    hasPrevious(kpi) {
        return kpi.previous !== undefined && kpi.previous !== null;
    }

    previous(kpi) {
        return formatValue(kpi.previous, kpi.type, {
            digits: this.props.report.digits,
            currencyId: this.props.report.currency_id,
        }) || "0";
    }

    delta(kpi) {
        if (kpi.delta_pct === false || kpi.delta_pct === undefined || kpi.delta_pct === null) {
            return "";
        }
        const sign = kpi.delta_pct > 0 ? "+" : "";
        return `${sign}${formatValue(kpi.delta_pct, "percent")}`;
    }

    format(kpi) {
        return formatValue(kpi.value, kpi.type, {
            digits: this.props.report.digits,
            currencyId: this.props.report.currency_id,
        }) || "0";
    }
}

/**
 * The report table. Header and total stick while scrolling; groups unfold;
 * rows open the record behind them; the ... menu opens the product in the
 * other reports.
 */
export class ReportTable extends Component {
    static template = "om_inventory_reports.ReportTable";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        rows: t.array(),
        columns: t.array(),
        total: t.object().optional(),
        report: t.object(),
        sort: t.or([t.object(), t.boolean()]).optional(),
        expanded: t.array(),
        focusedId: t.or([t.string(), t.boolean()]).optional(),
        groupLabel: t.string(),
        onToggle: t.function(),
        onOpen: t.function(),
        onLink: t.function(),
        onLoadMore: t.function(),
        onSort: t.function(),
        onFocus: t.function(),
    });

    /** The largest value of the bar column among each line's siblings. */
    get barMax() {
        const column = this.props.columns.find((c) => c.bar);
        const max = {};
        const count = {};
        if (!column) {
            return max;
        }
        for (const row of this.props.rows) {
            if (!["group", "leaf"].includes(row.kind)) {
                continue;
            }
            const value = Math.abs(row.values?.[column.key] || 0);
            const parent = row.parent_id || "root";
            max[parent] = Math.max(max[parent] || 0, value);
            count[parent] = (count[parent] || 0) + 1;
        }
        // a bar compares a line with its siblings: none for a line alone
        for (const parent in count) {
            if (count[parent] < 2) {
                delete max[parent];
            }
        }
        return max;
    }

    barStyle(row, column, barMax) {
        const max = barMax[row.parent_id || "root"];
        const value = Math.abs(row.values?.[column.key] || 0);
        if (!max || !["group", "leaf"].includes(row.kind)) {
            return false;
        }
        return `width: ${value ? Math.max(3, Math.round((value / max) * 100)) : 0}%`;
    }

    guides(row) {
        return Array.from({ length: Math.min(row.level || 0, 8) }, (_, i) => i);
    }

    isNumeric(column) {
        return NUMERIC.includes(column.type);
    }

    cell(row, column) {
        const value = row.values?.[column.key];
        if (column.detail_only && row.kind !== "detail") {
            return "";
        }
        if (this.isNumeric(column) && row.kind === "detail" && !value && column.key !== "balance") {
            return "";
        }
        return formatValue(value, column.type, {
            digits: this.props.report.digits,
            currencyId: this.props.report.currency_id,
        });
    }

    cellClass(row, column) {
        const value = row.values?.[column.key];
        const classes = [this.isNumeric(column) ? "text-end o_om_num" : "o_om_text"];
        if (this.isNumeric(column) && typeof value === "number") {
            if (value < 0) {
                classes.push("text-danger");
            } else if (value === 0 && row.kind !== "detail") {
                classes.push("o_om_zero");
            }
        }
        if (row.values?.[`${column.key}_tone`]) {
            classes.push(`o_om_tone_${row.values[`${column.key}_tone`]}`);
        }
        return classes.join(" ");
    }

    rowClass(row) {
        return {
            [`o_om_row_${row.kind}`]: true,
            [`o_om_level_${Math.min(row.level || 0, 6)}`]: true,
            o_om_clickable: row.has_children || row.open,
            o_om_expanded: this.props.expanded.includes(row.id),
            o_om_focused: this.props.focusedId === row.id,
        };
    }

    indent(row) {
        return `padding-left: ${0.75 + (row.level || 0) * 1.5}rem`;
    }

    sortIcon(column) {
        const sort = this.props.sort;
        if (!sort || sort.key !== column.key) {
            return "";
        }
        return sort.dir === "asc" ? "arrow_upward" : "arrow_downward";
    }

    onRowClick(row, ev) {
        if (ev.target.closest(".o_om_row_actions, .dropdown-menu")) {
            return;
        }
        this.props.onFocus(row.id);
        if (row.kind === "more") {
            this.props.onLoadMore(row.parentId);
        } else if (row.has_children) {
            this.props.onToggle(row);
        } else if (row.open) {
            this.props.onOpen(row);
        }
    }

    dimIcon(row) {
        return this.props.report.group_by.find((g) => g.key === row.dim)?.icon;
    }
}
