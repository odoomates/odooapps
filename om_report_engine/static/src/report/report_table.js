import { Component } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

import { DETAIL_KINDS, formatValue, headerGroups, NUMERIC } from "./format";

/**
 * The report table. The header (with its column groups) and the total stick
 * while scrolling; lines unfold; a line opens the record behind it or the
 * entries behind its figures; the ... menu opens the line in other reports.
 */
export class ReportTable extends Component {
    static template = "om_report_engine.ReportTable";
    static components = { Dropdown, DropdownItem };
    static props = {
        rows: Array,
        columns: Array,
        total: { type: [Object, Boolean], optional: true },
        report: Object,
        sort: { type: [Object, Boolean], optional: true },
        expanded: Array,
        focusedId: { type: [String, Boolean], optional: true },
        nameLabel: String,
        onToggle: Function,
        onOpen: Function,
        onDrill: Function,
        onLink: Function,
        onButton: Function,
        onCellDrill: Function,
        onNote: Function,
        onLoadMore: Function,
        onSort: Function,
        onFocus: Function,
    };

    get headerGroups() {
        return headerGroups(this.props.columns);
    }

    get sortable() {
        return this.props.report.group_by.length > 0;
    }

    guides(row) {
        return Array.from({ length: Math.min(row.level || 0, 8) }, (_, i) => i);
    }

    isNumeric(column) {
        return NUMERIC.includes(column.type);
    }

    cell(row, column) {
        if (column.detail_only && !DETAIL_KINDS.includes(row.kind)) {
            return "";
        }
        const value = row.values?.[column.key];
        if (column.blank_zero && value === 0 && row.kind === "detail") {
            return "";
        }
        return formatValue(value, row.types?.[column.key] || column.type, {
            digits: column.digits ?? 2,
            currencyId: this.props.report.currency_id,
            rounding: this.props.report.rounding,
        });
    }

    cellClass(row, column) {
        const value = row.values?.[column.key];
        const classes = [this.isNumeric(column) ? "text-end o_omr_num" : "o_omr_text"];
        if (this.isNumeric(column) && typeof value === "number") {
            // a residue of rounding (-0.0000001) is a zero, not a negative amount
            if (Math.abs(value) < 0.005) {
                classes.push("o_omr_zero");
            } else if (value < 0) {
                classes.push("text-danger");
            }
        }
        if (column.group) {
            classes.push("o_omr_grouped");
        }
        return classes.join(" ");
    }

    /** Whether a figure opens what makes it: a drillable column, a drillable line, a figure. */
    canDrillCell(row, column) {
        const value = row.values?.[column.key];
        return Boolean(column.drill && row.drill && typeof value === "number" && value !== 0);
    }

    onCellClick(row, column, ev) {
        if (this.canDrillCell(row, column)) {
            ev.stopPropagation();
            this.props.onFocus(row.id);
            this.props.onCellDrill(row, column);
        }
    }

    notesOf(row, column) {
        return row.notes?.[column.key] || [];
    }

    canNote(row, column) {
        return this.isNumeric(column) && !["loading", "more"].includes(row.kind) && row.kind !== "total";
    }

    noteTitle(row, column) {
        return this.notesOf(row, column)
            .map((note) => `${note.author}: ${note.note}`)
            .join("\n\n");
    }

    onNoteClick(row, column, ev) {
        ev.stopPropagation();
        this.props.onNote(row, column);
    }

    rowClass(row) {
        return {
            [`o_omr_row_${row.kind}`]: true,
            [`o_omr_level_${Math.min(row.level || 0, 6)}`]: true,
            o_omr_clickable: row.has_children || row.open || row.drill,
            o_omr_expanded: this.props.expanded.includes(row.id),
            o_omr_focused: this.props.focusedId === row.id,
        };
    }

    sortIcon(column) {
        const sort = this.props.sort;
        if (!sort || sort.key !== column.key) {
            return "";
        }
        return sort.dir === "asc" ? "arrow_upward" : "arrow_downward";
    }

    onRowClick(row, ev) {
        if (ev.target.closest(".o_omr_row_actions, .dropdown-menu")) {
            return;
        }
        this.props.onFocus(row.id);
        if (row.has_children) {
            this.props.onToggle(row);
        } else if (row.open) {
            this.props.onOpen(row);
        } else if (row.drill) {
            this.props.onDrill(row);
        }
    }
}
