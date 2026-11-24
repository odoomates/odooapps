import {
    Component,
    onMounted,
    onPatched,
    onWillUnmount,
    proxy,
    signal,
    useListener,
    useProps,
} from "@odoo/owl";

import { _t } from "@web/core/l10n/translation";
import { formatDate, formatDateTime } from "@web/core/l10n/dates";
import { usePopover } from "@web/core/popover/popover_hook";
import { formatFloat } from "@web/core/utils/numbers";
import { GanttPopover } from "./gantt_popover";

const LANE_HEIGHT = 34;
const ROW_PADDING = 6;
const STRIP_HEIGHT = 20;
const DRAG_THRESHOLD = 4;

export class GanttRenderer extends Component {
    static template = "om_web_gantt.GanttRenderer";
    static components = {};

    props = useProps([
        "model",
        "archInfo",
        "openRecord",
        "deleteRecord",
        "createRecord",
        "planRecords",
    ]);

    rootRef = signal.ref();
    gridRef = signal.ref();
    svgRef = signal.ref();

    setup() {
        this.state = proxy({
            folded: {},
            selection: null, // { rowKey, from, to } cells being selected
        });
        this.popover = usePopover(GanttPopover, {
            position: "bottom",
            onClose: () => this.clearPopoverHighlight(),
        });
        this.interaction = null;
        this.onPointerMove = this.onPointerMove.bind(this);
        this.onPointerUp = this.onPointerUp.bind(this);
        onMounted(() => this.drawDependencies());
        onPatched(() => this.drawDependencies());
        useListener(window, "resize", () => this.drawDependencies());
        onWillUnmount(() => this.stopListening());
    }

    get model() {
        return this.props.model;
    }

    get columns() {
        return this.model.data.columns;
    }

    get columnCount() {
        return this.columns.length || 1;
    }

    get rootStyle() {
        const minWidth = { day: 44, week: 110, month: 34, year: 70 }[this.model.scale];
        return `--o-gantt-columns: ${this.columnCount}; --o-gantt-cell-min: ${minWidth}px;`;
    }

    get cornerLabel() {
        const { groupBy } = this.model.data;
        if (!groupBy?.length) {
            return this.props.archInfo.string;
        }
        return groupBy
            .map((spec) => this.model.fields[spec.split(":")[0]]?.string || spec)
            .join(" / ");
    }

    get visibleRows() {
        const result = [];
        const visit = (rows) => {
            for (const row of rows) {
                result.push(row);
                if (row.isGroup && !this.state.folded[row.key]) {
                    visit(row.children);
                }
            }
        };
        visit(this.model.data.rows);
        return result;
    }

    get todayStyle() {
        const index = this.columns.findIndex((col) => col.isToday);
        if (index === -1) {
            return null;
        }
        const now = luxon.DateTime.local();
        const column = this.columns[index];
        const fraction = (now - column.start) / (column.stop - column.start);
        const position = (index + fraction) / this.columnCount;
        return `left: calc(var(--o-gantt-header-width) + (100% - var(--o-gantt-header-width)) * ${position});`;
    }

    get showTotalRow() {
        return this.props.archInfo.totalRow && this.model.data.rows.length > 0;
    }

    get hasConsolidation() {
        return Boolean(this.props.archInfo.consolidationField);
    }

    // -------------------------------------------------------------------------
    // Rendering helpers
    // -------------------------------------------------------------------------

    rowHeight(row) {
        if (row.isGroup) {
            return 30;
        }
        const strip = this.hasConsolidation ? STRIP_HEIGHT : 0;
        return row.laneCount * LANE_HEIGHT + ROW_PADDING * 2 + strip;
    }

    rowStyle(row) {
        return `height: ${this.rowHeight(row)}px;`;
    }

    rowHeaderStyle(row) {
        return `padding-left: ${0.75 + row.level * 1.1}rem;`;
    }

    spanStyle(left, width) {
        const n = this.columnCount;
        return `left: ${(left / n) * 100}%; width: ${(width / n) * 100}%;`;
    }

    pillStyle(pill) {
        const n = this.columnCount;
        const left = Math.max(pill.left, 0);
        const right = Math.min(pill.right, n);
        const top = ROW_PADDING + pill.lane * LANE_HEIGHT;
        return `left: ${(left / n) * 100}%; width: max(${((right - left) / n) * 100}%, 6px); top: ${top}px;`;
    }

    pillClass(pill, row) {
        const record = pill.record;
        const classes = [`o_gantt_color_${record.colorIndex}`];
        for (const decoration of record.decorations) {
            classes.push(`o_gantt_decoration_${decoration}`);
        }
        if (record.startsBefore) {
            classes.push("o_gantt_pill_starts_before");
        }
        if (record.stopsAfter) {
            classes.push("o_gantt_pill_stops_after");
        }
        if (this.model.canDrag) {
            classes.push("o_gantt_pill_draggable");
        }
        return classes.join(" ");
    }

    pillLabel(pill) {
        const record = pill.record;
        if (!this.props.archInfo.pillLabel) {
            return record.displayName;
        }
        return `${record.displayName} (${this.formatPeriod(record)})`;
    }

    pillTitle(pill) {
        return `${pill.record.displayName}\n${this.formatPeriod(pill.record)}`;
    }

    formatPeriod(record) {
        if (this.model.dateOnly) {
            const lastDay = record.stop.minus({ days: 1 });
            if (lastDay <= record.start) {
                return formatDate(record.start);
            }
            return `${formatDate(record.start)} - ${formatDate(lastDay)}`;
        }
        return `${formatDateTime(record.start)} - ${formatDateTime(record.stop)}`;
    }

    formatValue(value) {
        if (!this.hasConsolidation) {
            return String(value);
        }
        return formatFloat(value, { digits: [false, 2] });
    }

    aggregateTitle(aggregate, row) {
        if (!this.hasConsolidation) {
            return _t("%s records", aggregate.count);
        }
        const field = this.model.fields[this.props.archInfo.consolidationField];
        let title = `${field.string}: ${this.formatValue(aggregate.value)}`;
        if (row && row.consolidationMax !== null && row.consolidationMax !== undefined) {
            title += ` / ${this.formatValue(row.consolidationMax)}`;
        }
        return title;
    }

    progressBarTitle(row) {
        const bar = row.progressBar;
        return bar.label || `${this.formatNumber(bar.value)} / ${this.formatNumber(bar.max)}`;
    }

    formatNumber(value) {
        return formatFloat(value, { digits: [false, 2] });
    }

    isCellSelected(row, column) {
        const selection = this.state.selection;
        if (!selection || selection.rowKey !== row.key) {
            return false;
        }
        const from = Math.min(selection.from, selection.to);
        const to = Math.max(selection.from, selection.to);
        return column.index >= from && column.index <= to;
    }

    get canCreateInCells() {
        return this.model.canCreate;
    }

    get canPlanInCells() {
        return this.props.archInfo.activeActions.plan && this.model.canWrite && this.model.datesWritable;
    }

    // -------------------------------------------------------------------------
    // Rows
    // -------------------------------------------------------------------------

    toggleRow(row) {
        if (row.isGroup) {
            this.state.folded[row.key] = !this.state.folded[row.key];
        }
    }

    findRow(key) {
        const search = (rows) => {
            for (const row of rows) {
                if (row.key === key) {
                    return row;
                }
                const found = search(row.children);
                if (found) {
                    return found;
                }
            }
            return null;
        };
        return search(this.model.data.rows);
    }

    // -------------------------------------------------------------------------
    // Cells: create and plan
    // -------------------------------------------------------------------------

    getSelectionPeriod(from, to) {
        const first = this.model.getCellPeriod(Math.min(from, to));
        const last = this.model.getCellPeriod(Math.max(from, to));
        return { start: first.start, stop: last.stop };
    }

    onCellPointerDown(ev, row, column) {
        if (ev.button !== 0 || row.isGroup || !this.canCreateInCells) {
            return;
        }
        if (ev.target.closest(".o_gantt_cell_buttons")) {
            return;
        }
        ev.preventDefault();
        this.state.selection = { rowKey: row.key, from: column.index, to: column.index };
        this.interaction = { mode: "select", row };
        this.startListening();
    }

    onClickPlan(ev, row, column) {
        ev.stopPropagation();
        const period = this.model.getCellPeriod(column.index);
        this.props.planRecords({ ...period, row });
    }

    onClickCreate(ev, row, column) {
        ev.stopPropagation();
        const period = this.model.getCellPeriod(column.index);
        this.props.createRecord({ ...period, row });
    }

    // -------------------------------------------------------------------------
    // Pills: popover, drag and drop, resize
    // -------------------------------------------------------------------------

    clearPopoverHighlight() {
        const root = this.rootRef();
        root?.querySelectorAll(".o_gantt_pill_active").forEach((el) => {
            el.classList.remove("o_gantt_pill_active");
        });
    }

    openPopover(pillEl, record) {
        this.clearPopoverHighlight();
        pillEl.classList.add("o_gantt_pill_active");
        this.popover.open(pillEl, {
            model: this.model,
            record,
            openRecord: this.props.openRecord,
            deleteRecord: this.props.deleteRecord,
        });
    }

    onPillKeydown(ev, pill) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openPopover(ev.currentTarget, pill.record);
        }
    }

    onPillPointerDown(ev, pill, row, mode = "move") {
        if (ev.button !== 0) {
            return;
        }
        ev.stopPropagation();
        const pillEl = ev.currentTarget.closest(".o_gantt_pill");
        const draggable = this.model.canDrag;
        this.interaction = {
            mode: draggable ? mode : "click",
            pill,
            row,
            pillEl,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            deltaSteps: 0,
            targetRow: row,
        };
        if (draggable) {
            ev.preventDefault();
        }
        this.startListening();
    }

    startListening() {
        window.addEventListener("pointermove", this.onPointerMove);
        window.addEventListener("pointerup", this.onPointerUp);
    }

    stopListening() {
        window.removeEventListener("pointermove", this.onPointerMove);
        window.removeEventListener("pointerup", this.onPointerUp);
    }

    get columnWidth() {
        const cells = this.rootRef()?.querySelector(".o_gantt_header_cells");
        return cells ? cells.clientWidth / this.columnCount : 1;
    }

    columnAt(x, rowContentEl) {
        const rect = rowContentEl.getBoundingClientRect();
        const index = Math.floor(((x - rect.left) / rect.width) * this.columnCount);
        return Math.max(0, Math.min(this.columnCount - 1, index));
    }

    onPointerMove(ev) {
        const it = this.interaction;
        if (!it) {
            return;
        }
        if (it.mode === "select") {
            const rowEl = this.rootRef().querySelector(
                `.o_gantt_row[data-row-key='${CSS.escape(it.row.key)}'] .o_gantt_row_content`
            );
            if (rowEl) {
                const to = this.columnAt(ev.clientX, rowEl);
                if (this.state.selection && this.state.selection.to !== to) {
                    this.state.selection.to = to;
                }
            }
            return;
        }
        const dx = ev.clientX - it.startX;
        const dy = ev.clientY - it.startY;
        if (!it.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) {
            return;
        }
        if (it.mode === "click") {
            return;
        }
        if (!it.moved) {
            it.moved = true;
            this.popover.close();
            it.ghost = it.pillEl.cloneNode(true);
            it.ghost.classList.add("o_gantt_pill_ghost");
            it.ghost.removeAttribute("data-record-id");
            it.pillEl.parentElement.appendChild(it.ghost);
            it.pillEl.classList.add("o_gantt_pill_dragged");
            this.rootRef().classList.add("o_gantt_dragging");
        }
        const steps = this.model.stepsPerColumn;
        const width = this.columnWidth;
        it.deltaSteps = Math.round((dx / width) * steps);
        const deltaPx = (it.deltaSteps / steps) * width;
        if (it.mode === "move") {
            let deltaY = 0;
            const target = this.rowElementAt(ev.clientX, ev.clientY);
            const originEl = it.pillEl.closest(".o_gantt_row");
            this.rootRef()
                .querySelectorAll(".o_gantt_row_drop_target")
                .forEach((el) => el.classList.remove("o_gantt_row_drop_target"));
            it.targetRow = it.row;
            if (target && target !== originEl) {
                const targetRow = this.findRow(target.dataset.rowKey);
                if (targetRow && !targetRow.isGroup && this.model.canMoveToRow(it.row, targetRow)) {
                    it.targetRow = targetRow;
                    target.classList.add("o_gantt_row_drop_target");
                    deltaY = target.getBoundingClientRect().top - originEl.getBoundingClientRect().top;
                }
            }
            it.ghost.style.transform = `translate(${deltaPx}px, ${deltaY}px)`;
        } else {
            const rect = it.pillEl.getBoundingClientRect();
            const minWidth = Math.max(width / steps, 6);
            if (it.mode === "start") {
                const maxDelta = rect.width - minWidth;
                const px = Math.min(deltaPx, maxDelta);
                it.deltaSteps = Math.round((px / width) * steps);
                it.ghost.style.transform = `translateX(${px}px)`;
                it.ghost.style.width = `${rect.width - px}px`;
            } else {
                const px = Math.max(deltaPx, minWidth - rect.width);
                it.deltaSteps = Math.round((px / width) * steps);
                it.ghost.style.width = `${rect.width + px}px`;
            }
        }
    }

    rowElementAt(x, y) {
        const el = document.elementFromPoint(x, y);
        return el?.closest(".o_gantt_row[data-row-key]") || null;
    }

    /**
     * Shifts a date by a number of snapping steps of the current scale.
     */
    shiftDate(date, deltaSteps) {
        const steps = this.model.stepsPerColumn;
        switch (this.model.scale) {
            case "day":
                return date.plus({ minutes: Math.round((deltaSteps * 60) / steps) });
            case "year": {
                if (steps >= 2) {
                    const months = Math.trunc(deltaSteps / 2);
                    const half = deltaSteps - months * 2;
                    return date.plus({ months, days: half * 15 });
                }
                return date.plus({ months: deltaSteps });
            }
            default:
                return date.plus({ minutes: Math.round((deltaSteps * 24 * 60) / steps) });
        }
    }

    async onPointerUp(ev) {
        const it = this.interaction;
        this.interaction = null;
        this.stopListening();
        if (!it) {
            return;
        }
        if (it.mode === "select") {
            const selection = this.state.selection;
            this.state.selection = null;
            if (selection) {
                const period = this.getSelectionPeriod(selection.from, selection.to);
                this.props.createRecord({ ...period, row: it.row });
            }
            return;
        }
        if (!it.moved) {
            this.openPopover(it.pillEl, it.pill.record);
            return;
        }
        const record = it.pill.record;
        const params = {};
        if (it.mode === "move") {
            if (it.deltaSteps) {
                params.start = this.shiftDate(record.start, it.deltaSteps);
                params.stop = this.shiftDate(record.stop, it.deltaSteps);
            }
            params.fromRow = it.row;
            params.toRow = it.targetRow;
        } else if (it.mode === "start" && it.deltaSteps) {
            params.start = this.shiftDate(record.start, it.deltaSteps);
        } else if (it.mode === "stop" && it.deltaSteps) {
            params.stop = this.shiftDate(record.stop, it.deltaSteps);
        }
        try {
            await this.model.reschedule(record.id, params);
        } finally {
            it.ghost?.remove();
            it.pillEl.classList.remove("o_gantt_pill_dragged");
            const root = this.rootRef();
            root?.classList.remove("o_gantt_dragging");
            root?.querySelectorAll(".o_gantt_row_drop_target").forEach((el) => {
                el.classList.remove("o_gantt_row_drop_target");
            });
        }
    }

    // -------------------------------------------------------------------------
    // Dependencies
    // -------------------------------------------------------------------------

    drawDependencies() {
        const svg = this.svgRef();
        const grid = this.gridRef();
        if (!svg || !grid) {
            return;
        }
        if (!this.props.archInfo.dependencyField) {
            svg.replaceChildren();
            return;
        }
        const gridRect = grid.getBoundingClientRect();
        const elements = {};
        for (const el of grid.querySelectorAll(".o_gantt_pill[data-record-id]")) {
            elements[el.dataset.recordId] ||= el;
        }
        const paths = [];
        const records = this.model.data.records;
        for (const record of Object.values(records)) {
            const toEl = elements[record.id];
            if (!toEl) {
                continue;
            }
            for (const depId of record.dependencies) {
                const fromEl = elements[depId];
                if (!fromEl || !records[depId]) {
                    continue;
                }
                const from = fromEl.getBoundingClientRect();
                const to = toEl.getBoundingClientRect();
                const x1 = from.right - gridRect.left;
                const y1 = from.top + from.height / 2 - gridRect.top;
                const x2 = to.left - gridRect.left;
                const y2 = to.top + to.height / 2 - gridRect.top;
                const bend = Math.max(Math.abs(x2 - x1) / 2, 24);
                const late = records[depId].stop > record.start;
                paths.push(
                    `<path d="M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2 - 2} ${y2}" class="${
                        late ? "o_gantt_dependency_late" : "o_gantt_dependency"
                    }" marker-end="url(#${late ? "o_gantt_arrow_late" : "o_gantt_arrow"})"/>`
                );
            }
        }
        svg.setAttribute("width", grid.scrollWidth);
        svg.setAttribute("height", grid.scrollHeight);
        svg.innerHTML = `<defs>
            <marker id="o_gantt_arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" class="o_gantt_dependency_head"/></marker>
            <marker id="o_gantt_arrow_late" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" class="o_gantt_dependency_head_late"/></marker>
        </defs>${paths.join("")}`;
    }
}
