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
