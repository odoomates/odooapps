import { Component, t, useProps } from "@odoo/owl";

import { formatValue } from "./format";

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
    static template = "om_report_engine.ReportChart";
    props = useProps({
        chart: t.object(),
        report: t.object(),
        active: t.or([t.string(), t.boolean()]).optional(),
        onSelect: t.function(),
    });

    format(value, type) {
        type = type || this.props.chart.value_type;
        return formatValue(value, type, {
            digits: type === "float" ? this.props.report.digits : undefined,
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
        return `--omr-cell-strength: ${strength.toFixed(3)}`;
    }

    itemClass(item) {
        const classes = [`o_omr_tone_${item.tone || "neutral"}`];
        if (item.filter) {
            classes.push("o_omr_chart_filter");
            if (item.filter === this.props.active) {
                classes.push("o_omr_chart_active");
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
    static template = "om_report_engine.KpiCards";
    props = useProps({
        kpis: t.array(),
        active: t.or([t.string(), t.boolean()]).optional(),
        report: t.object(),
        onSelect: t.function(),
    });

    kpiClass(kpi) {
        const classes = [`o_omr_tone_${kpi.tone || "neutral"}`];
        if (kpi.filter) {
            classes.push("o_omr_kpi_filter");
            if (kpi.filter === this.props.active) {
                classes.push("o_omr_kpi_active");
            }
        }
        return classes.join(" ");
    }

    hasPrevious(kpi) {
        return kpi.previous !== undefined && kpi.previous !== null;
    }

    previous(kpi) {
        return formatValue(kpi.previous, kpi.type, {
            digits: kpi.type === "float" ? this.props.report.digits : undefined,
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
            digits: kpi.type === "float" ? this.props.report.digits : undefined,
            currencyId: this.props.report.currency_id,
        }) || "0";
    }
}
