import { Component, markup, onWillStart, proxy, signal, useEffect, useListener, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "om.report.design";
const PX_PER_MM = 96 / 25.4;
const PX_PER_PT = 96 / 72;
// edges closer than this on screen snap together
const SNAP_PX = 6;
// a click that moves less than this is not a drag
const DRAG_THRESHOLD_PX = 3;
const HISTORY_SIZE = 100;
const NUMERIC = ["integer", "float", "monetary"];

export const PAPERS = {
    A4: [210, 297],
    A5: [148, 210],
    Letter: [215.9, 279.4],
    Legal: [215.9, 355.6],
};
const BAND_RANK = { page_header: 0, report_header: 1, record: 2, table: 2, report_footer: 3, page_footer: 4 };
const SINGLE_BANDS = ["page_header", "report_header", "report_footer", "page_footer"];

export const BAND_KINDS = {
    page_header: { label: _t("Page Header"), hint: _t("top of every page") },
    report_header: { label: _t("Report Header"), hint: _t("once, before the first record") },
    record: { label: _t("Record"), hint: _t("for each record") },
    table: { label: _t("Lines"), hint: _t("one row per line, for each record") },
    report_footer: { label: _t("Report Footer"), hint: _t("once, after the last record") },
    page_footer: { label: _t("Page Footer"), hint: _t("bottom of every page") },
};

export const TOOLS = [
    { type: "text", label: _t("Text"), symbol: "T", size: [40, 6] },
    { type: "line", label: _t("Line"), symbol: "─", size: [50, 0.3] },
    { type: "box", label: _t("Box"), symbol: "▭", size: [50, 15] },
    { type: "image", label: _t("Company Logo"), symbol: "▣", size: [40, 15] },
    { type: "page", label: _t("Page Number"), symbol: "#", size: [40, 6] },
    { type: "date", label: _t("Print Date"), symbol: "◷", size: [30, 6] },
];

const FORMATS = [
    ["auto", _t("Automatic")],
    ["number", _t("Number")],
    ["monetary", _t("Amount with currency")],
    ["date", _t("Date")],
    ["datetime", _t("Date and time")],
    ["image", _t("Image")],
];

let lastId = 0;
function newId(prefix) {
    lastId += 1;
    return `${prefix}${Date.now().toString(36)}${lastId}`;
}

function round(value, digits = 2) {
    const factor = 10 ** digits;
    return Math.round(value * factor) / factor;
}

function defaultStyle(style = {}) {
    return {
        font_size: 10,
        bold: false,
        italic: false,
        underline: false,
        color: "",
        background: "",
        align: "left",
        valign: "middle",
        border: false,
        border_color: "",
        border_width: 0.3,
        wrap: false,
        ...style,
    };
}

/**
 * The report designer: the page of a report with its bands, the fields of
 * the model to drag on it, and the properties of what is selected. Sizes
 * are kept in millimetres, as the PDF prints them, and drawn at the zoom.
 */
export class ReportDesigner extends Component {
    static template = "om_report_designer.Designer";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.designId = this.props.action.params?.design_id || this.props.action.context?.active_id;

        this.BAND_KINDS = BAND_KINDS;
        this.TOOLS = TOOLS;
        this.FORMATS = FORMATS;
        this.PAPERS = Object.keys(PAPERS);
        this.GEOMETRY = [["x", _t("Left")], ["y", _t("Top")], ["w", _t("Width")], ["h", _t("Height")]];
        this.MARGINS = [
            ["margin_top", _t("Top")],
            ["margin_bottom", _t("Bottom")],
            ["margin_left", _t("Left")],
            ["margin_right", _t("Right")],
        ];

        this.state = proxy({
            loaded: false,
            settings: {},
            layout: { bands: [] },
            companyId: false,
            records: [],
            fields: {},
            expanded: {},
            search: "",
            selection: [],
            bandId: null,
            columnId: null,
            editing: null,
            guides: [],
            dropBandId: null,
            columnDrop: null,
            zoom: 1,
            grid: 1,
            snap: true,
            withLabel: true,
            mode: "design",
            previewHtml: "",
            previewRecordId: false,
            previewLoading: false,
            dirty: false,
            saved: false,
            saving: false,
            undoCount: 0,
            redoCount: 0,
        });
        this.undoStack = [];
        this.redoStack = [];
        this.clipboard = null;
        this.drag = null;
        this.dragPayload = null;

        this.editRef = signal.ref();
        useEffect(() => {
            const input = this.editRef();
            if (input) {
                input.focus();
                input.select();
            }
        });
        useListener(document, "pointermove", (ev) => this.onPointerMove(ev));
        useListener(document, "pointerup", (ev) => this.onPointerUp(ev));
        useListener(document, "keydown", (ev) => this.onKeyDown(ev));
        useListener(window, "beforeunload", (ev) => {
            if (this.state.dirty) {
                ev.preventDefault();
                ev.returnValue = "";
            }
        });
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------------
    // loading
    // ------------------------------------------------------------------

    async load() {
        const data = await this.orm.call(MODEL, "designer_load", [[this.designId]]);
        this.state.settings = data.settings;
        this.state.layout = data.layout;
        this.state.records = data.records;
        this.state.companyId = data.company_id;
        this.state.previewRecordId = data.records[0]?.id || false;
        await this.loadFields(data.settings.model);
        for (const band of data.layout.bands) {
            if (band.kind === "table") {
                const field = this.fieldOf(data.settings.model, band.relation);
                if (field?.relation) {
                    this.state.expanded[band.relation] = true;
                    await this.loadFields(field.relation);
                }
            }
        }
        this.state.loaded = true;
    }

    async loadFields(model) {
        if (!model || this.state.fields[model]) {
            return;
        }
        this.state.fields[model] = await this.orm.call(MODEL, "designer_fields", [model]);
    }

    fieldOf(model, name) {
        return (this.state.fields[model] || []).find((field) => field.name === name);
    }

    /** Labels of the fields of a path, as far as they are loaded. */
    pathLabels(model, path) {
        const labels = [];
        for (const name of (path || "").split(".")) {
            const field = this.fieldOf(model, name);
            if (!field) {
                labels.push(name);
                break;
            }
            labels.push(field.label);
            model = field.relation;
        }
        return labels;
    }

    pathLabel(model, path) {
        return this.pathLabels(model, path).join(" › ");
    }

    // ------------------------------------------------------------------
    // page
    // ------------------------------------------------------------------

    get pageSize() {
        const [width, height] = PAPERS[this.state.settings.paper] || PAPERS.A4;
        return this.state.settings.orientation === "landscape" ? [height, width] : [width, height];
    }

    get printableWidth() {
        const settings = this.state.settings;
        return round(this.pageSize[0] - (settings.margin_left || 0) - (settings.margin_right || 0));
    }

    get scale() {
        return PX_PER_MM * this.state.zoom;
    }

    px(mm) {
        return round(mm * this.scale);
    }

    toMm(px) {
        return px / this.scale;
    }

    snap(mm) {
        if (!this.state.snap) {
            return round(mm, 1);
        }
        const grid = this.state.grid || 1;
        return round(Math.round(mm / grid) * grid);
    }

    get sheetStyle() {
        const settings = this.state.settings;
        return [
            `width:${this.px(this.pageSize[0])}px`,
            `padding:${this.px(settings.margin_top)}px ${this.px(settings.margin_right)}px `
                + `${this.px(settings.margin_bottom)}px ${this.px(settings.margin_left)}px`,
        ].join(";");
    }

    bandBodyStyle(band) {
        const grid = this.px(this.state.grid || 1);
        const css = [`width:${this.px(this.printableWidth)}px`, `height:${this.px(band.height)}px`];
        if (grid >= 4) {
            css.push(`background-size:${grid}px ${grid}px`);
        }
        return css.join(";");
    }

    bandTitle(band) {
        const kind = BAND_KINDS[band.kind];
        if (band.kind === "table") {
            return `${kind.label}: ${this.pathLabel(this.state.settings.model, band.relation)}`;
        }
        return kind.label;
    }

    bandHint(band) {
        if (band.kind === "record") {
            return _t("for each %s", this.state.settings.model_name);
        }
        return BAND_KINDS[band.kind].hint;
    }

    // ------------------------------------------------------------------
    // elements on the page
    // ------------------------------------------------------------------

    elementStyle(element) {
        const style = element.style || {};
        const css = [
            `left:${this.px(element.x)}px`,
            `top:${this.px(element.y)}px`,
            `width:${this.px(element.w)}px`,
            `height:${Math.max(this.px(element.h), element.type === "line" ? 1 : 0)}px`,
        ];
        if (element.type === "line") {
            css.push(`background-color:${style.color || "#000000"}`);
            return css.join(";");
        }
        if (style.background) {
            css.push(`background-color:${style.background}`);
        }
        if (style.border || element.type === "box") {
            const width = Math.max(1, this.px(style.border_width || 0.3));
            css.push(`border:${width}px solid ${style.border_color || "#000000"}`);
        }
        return css.join(";");
    }

    cellStyle(element) {
        const style = element.style || {};
        const valign = { top: "flex-start", middle: "center", bottom: "flex-end" }[style.valign || "middle"];
        const css = [
            `justify-content:${valign}`,
            `text-align:${style.align || "left"}`,
            `font-size:${round((style.font_size || 10) * PX_PER_PT * this.state.zoom)}px`,
            `padding:0 ${this.px(0.5)}px`,
            `white-space:${style.wrap ? "normal" : "nowrap"}`,
        ];
        if (style.bold) {
            css.push("font-weight:bold");
        }
        if (style.italic) {
            css.push("font-style:italic");
        }
        if (style.underline) {
            css.push("text-decoration:underline");
        }
        if (style.color) {
            css.push(`color:${style.color}`);
        }
        return css.join(";");
    }

    elementText(element) {
        switch (element.type) {
            case "text":
                return element.text || "";
            case "page":
                return (element.text || "{page} / {pages}").replaceAll("{page}", "1").replaceAll("{pages}", "1");
            case "date":
                return element.format === "datetime" ? _t("[Print Date and Time]") : _t("[Print Date]");
            case "field": {
                const model = element.source === "company" ? "res.company" : this.state.settings.model;
                return `[${this.pathLabels(model, element.field).join(" ")}]`;
            }
        }
        return "";
    }

    elementTypeLabel(type) {
        return {
            text: _t("Text"),
            field: _t("Field"),
            line: _t("Line"),
            box: _t("Box"),
            image: _t("Image"),
            page: _t("Page Number"),
            date: _t("Print Date"),
        }[type];
    }

    digitsValue(digits) {
        return digits === null || digits === undefined ? "" : digits;
    }

    get logoUrl() {
        return `/web/image/res.company/${this.state.companyId}/logo`;
    }

    isSelected(element) {
        return this.state.selection.includes(element.id);
    }

    get selectedElements() {
        const result = [];
        for (const band of this.state.layout.bands) {
            for (const element of band.elements || []) {
                if (this.state.selection.includes(element.id)) {
                    result.push(element);
                }
            }
        }
        return result;
    }

    get selectedBand() {
        return this.state.layout.bands.find((band) => band.id === this.state.bandId);
    }

    get selectedColumn() {
        const band = this.selectedBand;
        return band?.kind === "table" && band.columns.find((column) => column.id === this.state.columnId);
    }

    bandOf(elementId) {
        return this.state.layout.bands.find((band) => (band.elements || []).some((el) => el.id === elementId));
    }

    select(band, element = null, add = false) {
        this.state.bandId = band?.id || null;
        this.state.columnId = null;
        if (!element) {
            this.state.selection = [];
        } else if (add) {
            const selection = this.state.selection.filter((id) => this.bandOf(id)?.id === band.id);
            this.state.selection = selection.includes(element.id)
                ? selection.filter((id) => id !== element.id)
                : [...selection, element.id];
        } else if (!this.isSelected(element)) {
            this.state.selection = [element.id];
        }
    }

    clearSelection() {
        this.state.selection = [];
        this.state.columnId = null;
        this.state.bandId = null;
        this.state.editing = null;
    }

    // ------------------------------------------------------------------
    // history
    // ------------------------------------------------------------------

    snapshot() {
        return JSON.stringify(this.state.layout);
    }

    commit(change) {
        const before = this.snapshot();
        change();
        this.pushUndo(before);
    }

    pushUndo(before) {
        if (before === this.snapshot()) {
            return;
        }
        this.undoStack.push(before);
        if (this.undoStack.length > HISTORY_SIZE) {
            this.undoStack.shift();
        }
        this.redoStack = [];
        this.state.dirty = true;
        this.updateHistory();
    }

    updateHistory() {
        this.state.undoCount = this.undoStack.length;
        this.state.redoCount = this.redoStack.length;
    }

    undo() {
        if (this.undoStack.length) {
            this.redoStack.push(this.snapshot());
            this.restoreLayout(this.undoStack.pop());
        }
    }

    redo() {
        if (this.redoStack.length) {
            this.undoStack.push(this.snapshot());
            this.restoreLayout(this.redoStack.pop());
        }
    }

    restoreLayout(json) {
        this.state.layout = JSON.parse(json);
        const ids = new Set(this.state.layout.bands.flatMap((band) => (band.elements || []).map((el) => el.id)));
        this.state.selection = this.state.selection.filter((id) => ids.has(id));
        if (!this.selectedBand) {
            this.state.bandId = null;
        }
        this.state.editing = null;
        this.state.dirty = true;
        this.updateHistory();
    }

    // ------------------------------------------------------------------
    // fields list
    // ------------------------------------------------------------------

    get fieldRows() {
        const rows = [];
        const search = this.state.search.trim().toLowerCase();
        const walk = (model, prefix, labels, depth) => {
            for (const field of this.state.fields[model] || []) {
                const path = prefix ? `${prefix}.${field.name}` : field.name;
                const expanded = Boolean(this.state.expanded[path]);
                if (depth === 0 && search && !expanded
                    && !field.label.toLowerCase().includes(search) && !field.name.includes(search)) {
                    continue;
                }
                const row = {
                    ...field,
                    path,
                    depth,
                    expanded,
                    labels: [...labels, field.label],
                    relational: Boolean(field.relation),
                };
                rows.push(row);
                if (row.relational && expanded && depth < 3) {
                    walk(field.relation, path, row.labels, depth + 1);
                }
            }
        };
        walk(this.state.settings.model, "", [], 0);
        return rows;
    }

    async toggleField(row) {
        if (!row.relational) {
            return;
        }
        if (!row.expanded) {
            await this.loadFields(row.relation);
        }
        this.state.expanded[row.path] = !row.expanded;
    }

    fieldIcon(row) {
        if (row.x2many) {
            return "☰";
        }
        if (row.relational) {
            return "→";
        }
        if (NUMERIC.includes(row.type)) {
            return "#";
        }
        if (row.type === "date" || row.type === "datetime") {
            return "◷";
        }
        if (row.type === "binary") {
            return "▣";
        }
        return "a";
    }

    onFieldDragStart(ev, row) {
        this.dragPayload = { kind: "field", ...row };
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", row.path);
    }

    onToolDragStart(ev, tool) {
        this.dragPayload = { kind: "tool", type: tool.type };
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", tool.type);
    }

    onDragEnd() {
        this.dragPayload = null;
        this.state.dropBandId = null;
        this.state.columnDrop = null;
    }

    /** Double click on a field, or click on a tool: add it to the selected band. */
    targetBand() {
        const band = this.selectedBand;
        if (band) {
            return band;
        }
        return this.state.layout.bands.find((b) => b.kind === "record") || this.state.layout.bands[0];
    }

    addFieldToBand(row) {
        const band = this.targetBand();
        if (!band) {
            return;
        }
        if (band.kind === "table") {
            this.addColumn(band, row, band.columns.length);
            return;
        }
        const bottom = Math.max(0, ...band.elements.map((el) => el.y + el.h));
        this.addField(band, row, 0, this.snap(bottom + (band.elements.length ? 1 : 0)));
    }

    addToolToBand(tool) {
        const band = this.targetBand();
        if (!band || band.kind === "table") {
            this.notification.add(_t("Select a band of the page first."), { type: "warning" });
            return;
        }
        this.addTool(band, tool.type, 0, 0);
    }

    // ------------------------------------------------------------------
    // dropping on bands
    // ------------------------------------------------------------------

    onBandDragOver(ev, band) {
        if (this.dragPayload) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "copy";
            this.state.dropBandId = band.id;
        }
    }

    onBandDragLeave(ev, band) {
        if (this.state.dropBandId === band.id && !ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.dropBandId = null;
        }
    }

    onBandDrop(ev, band) {
        ev.preventDefault();
        const payload = this.dragPayload;
        this.onDragEnd();
        if (!payload) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const x = this.snap(this.toMm(ev.clientX - rect.left));
        const y = this.snap(this.toMm(ev.clientY - rect.top));
        if (payload.kind === "tool") {
            this.addTool(band, payload.type, x, y);
        } else {
            this.addField(band, payload, x, y);
        }
    }

    fitInBand(band, element) {
        element.w = Math.min(element.w, this.printableWidth);
        element.x = round(Math.max(0, Math.min(element.x, this.printableWidth - element.w)));
        element.y = round(Math.max(0, element.y));
        if (element.y + element.h > band.height) {
            band.height = round(element.y + element.h);
        }
    }

    addTool(band, type, x, y) {
        const tool = TOOLS.find((t) => t.type === type);
        const element = {
            id: newId("e"),
            type,
            x,
            y,
            w: tool.size[0],
            h: tool.size[1],
            style: defaultStyle(type === "page" ? { align: "right", font_size: 8 } : {}),
        };
        if (type === "text") {
            element.text = _t("Text");
        } else if (type === "page") {
            element.text = _t("Page {page} / {pages}");
        } else if (type === "image") {
            element.source = "company";
            element.field = "logo";
        } else if (type === "date") {
            element.format = "date";
        }
        this.commit(() => {
            this.fitInBand(band, element);
            band.elements.push(element);
        });
        this.select(band, element);
        if (type === "text") {
            this.startEdit(element);
        }
    }

    addField(band, row, x, y) {
        if (row.x2many && !row.path.includes(".")) {
            if (band.kind !== "record") {
                this.notification.add(
                    _t("Drop “%s” on a Record band: it adds a table of its lines under that band.", row.label),
                    { type: "warning" }
                );
                return;
            }
            this.addTable(band, row);
            return;
        }
        const image = row.type === "binary";
        const numeric = NUMERIC.includes(row.type);
        const elements = [];
        let fieldX = x;
        if (this.state.withLabel && !image) {
            elements.push({
                id: newId("e"),
                type: "text",
                text: `${row.labels.join(" ")}:`,
                x,
                y,
                w: 30,
                h: 6,
                style: defaultStyle({ bold: true }),
            });
            fieldX = x + 31;
        }
        elements.push({
            id: newId("e"),
            type: "field",
            source: "record",
            field: row.path,
            format: image ? "image" : "auto",
            digits: null,
            x: fieldX,
            y,
            w: image ? 30 : 50,
            h: image ? 20 : 6,
            style: defaultStyle({ align: numeric ? "right" : "left" }),
        });
        this.commit(() => {
            for (const element of elements) {
                this.fitInBand(band, element);
                band.elements.push(element);
            }
        });
        this.state.bandId = band.id;
        this.state.columnId = null;
        this.state.selection = elements.map((el) => el.id);
    }

    async addTable(band, row) {
        await this.loadFields(row.relation);
        this.state.expanded[row.path] = true;
        const lineFields = this.state.fields[row.relation] || [];
        const table = {
            id: newId("b"),
            kind: "table",
            relation: row.path,
            domain: lineFields.some((f) => f.name === "display_type") ? "[('display_type', '=', False)]" : "",
            order: "",
            x: 0,
            font_size: 9,
            row_height: 6,
            header_bg: "#e9ecef",
            header_color: "",
            border: true,
            stripe: false,
            columns: [],
        };
        this.commit(() => {
            const bands = this.state.layout.bands;
            bands.splice(bands.indexOf(band) + 1, 0, table);
        });
        this.state.selection = [];
        this.state.bandId = table.id;
    }

    // ------------------------------------------------------------------
    // tables
    // ------------------------------------------------------------------

    tableWidth(band) {
        return band.columns.reduce((total, column) => total + column.width, 0);
    }

    tableModel(band) {
        return this.fieldOf(this.state.settings.model, band.relation)?.relation;
    }

    columnLabel(band, column) {
        return this.pathLabel(this.tableModel(band), column.field);
    }

    tableRowStyle(band) {
        return `height:${this.px(band.row_height)}px;font-size:${round(band.font_size * PX_PER_PT * this.state.zoom)}px`;
    }

    columnIndexAt(band, ev, container) {
        const left = container.getBoundingClientRect().left;
        let position = this.toMm(ev.clientX - left);
        let index = 0;
        for (const column of band.columns) {
            if (position < column.width / 2) {
                return index;
            }
            position -= column.width;
            index += 1;
        }
        return index;
    }

    onTableDragOver(ev, band) {
        if (this.dragPayload) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "copy";
            this.state.dropBandId = band.id;
            const header = ev.currentTarget.querySelector(".o_om_rd_dtable_head");
            this.state.columnDrop = { bandId: band.id, index: this.columnIndexAt(band, ev, header) };
        }
    }

    onTableDrop(ev, band) {
        ev.preventDefault();
        const payload = this.dragPayload;
        const index = this.state.columnDrop?.index ?? band.columns.length;
        this.onDragEnd();
        if (!payload) {
            return;
        }
        if (payload.kind === "tool") {
            this.notification.add(_t("Tables take fields of their lines only."), { type: "warning" });
            return;
        }
        this.addColumn(band, payload, index);
    }

    addColumn(band, row, index) {
        const prefix = `${band.relation}.`;
        if (!row.path.startsWith(prefix)) {
            this.notification.add(
                _t("Drag the fields listed under “%s” into this table.", this.pathLabel(this.state.settings.model, band.relation)),
                { type: "warning" }
            );
            return;
        }
        const numeric = NUMERIC.includes(row.type);
        const free = this.printableWidth - band.x - this.tableWidth(band);
        const column = {
            id: newId("c"),
            field: row.path.slice(prefix.length),
            label: row.labels.slice(1).join(" "),
            width: round(Math.max(10, Math.min(numeric ? 25 : 40, free))),
            align: numeric ? "right" : "left",
            format: row.type === "binary" ? "image" : "auto",
            digits: null,
            sum: false,
        };
        this.commit(() => band.columns.splice(index, 0, column));
        this.state.bandId = band.id;
        this.state.columnId = column.id;
        this.state.selection = [];
        if (free < 10) {
            this.notification.add(_t("The table is wider than the page: make some columns narrower."), {
                type: "warning",
            });
        }
    }

    onColumnPointerDown(ev, band, column) {
        if (ev.button !== 0 || this.state.mode !== "design") {
            return;
        }
        this.state.bandId = band.id;
        this.state.columnId = column.id;
        this.state.selection = [];
        const header = ev.currentTarget.closest(".o_om_rd_dtable_head");
        this.drag = {
            type: "column",
            band,
            column,
            header,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            before: this.snapshot(),
        };
    }

    onColumnResizeStart(ev, band, column) {
        this.state.bandId = band.id;
        this.state.columnId = column.id;
        this.state.selection = [];
        this.drag = {
            type: "column-resize",
            band,
            column,
            origin: column.width,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            before: this.snapshot(),
        };
    }

    // ------------------------------------------------------------------
    // moving and resizing
    // ------------------------------------------------------------------

    onElementPointerDown(ev, band, element) {
        if (ev.button !== 0 || this.state.mode !== "design" || this.state.editing?.id === element.id) {
            return;
        }
        ev.preventDefault();
        this.select(band, element, ev.shiftKey || ev.ctrlKey || ev.metaKey);
        if (!this.isSelected(element)) {
            return;
        }
        this.drag = {
            type: "move",
            band,
            element,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            before: this.snapshot(),
            grabY: this.toMm(ev.clientY - ev.currentTarget.getBoundingClientRect().top),
            origins: Object.fromEntries(this.selectedElements.map((el) => [el.id, { x: el.x, y: el.y }])),
        };
    }

    onHandlePointerDown(ev, band, element, dir) {
        ev.preventDefault();
        this.drag = {
            type: "resize",
            band,
            element,
            dir,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            before: this.snapshot(),
            origin: { x: element.x, y: element.y, w: element.w, h: element.h },
        };
    }

    onBandResizeStart(ev, band) {
        ev.preventDefault();
        this.state.bandId = band.id;
        this.drag = {
            type: "band",
            band,
            origin: band.height,
            startX: ev.clientX,
            startY: ev.clientY,
            moved: false,
            before: this.snapshot(),
        };
    }

    onBandPointerDown(ev, band) {
        if (ev.button === 0 && this.state.mode === "design") {
            this.select(band);
            this.state.editing = null;
        }
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        const dxPx = ev.clientX - drag.startX;
        const dyPx = ev.clientY - drag.startY;
        if (!drag.moved) {
            if (Math.abs(dxPx) < DRAG_THRESHOLD_PX && Math.abs(dyPx) < DRAG_THRESHOLD_PX) {
                return;
            }
            drag.moved = true;
            document.body.classList.add("o_om_rd_dragging");
        }
        const dx = this.toMm(dxPx);
        const dy = this.toMm(dyPx);
        switch (drag.type) {
            case "move":
                this.moveSelection(drag, dx, dy);
                break;
            case "resize":
                this.resizeElement(drag, dx, dy);
                break;
            case "band": {
                const content = Math.max(1, ...drag.band.elements.map((el) => el.y + el.h));
                drag.band.height = Math.max(round(content), this.snap(drag.origin + dy));
                break;
            }
            case "column-resize":
                drag.column.width = Math.max(3, this.snap(drag.origin + dx));
                break;
            case "column":
                this.state.columnDrop = {
                    bandId: drag.band.id,
                    index: this.columnIndexAt(drag.band, ev, drag.header),
                };
                break;
        }
    }

    onPointerUp(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        this.drag = null;
        document.body.classList.remove("o_om_rd_dragging");
        this.state.guides = [];
        if (!drag.moved) {
            return;
        }
        if (drag.type === "move" && this.state.selection.length === 1) {
            this.dropInOtherBand(ev, drag);
        }
        if (drag.type === "column") {
            const index = this.state.columnDrop?.index;
            this.state.columnDrop = null;
            const columns = drag.band.columns;
            const from = columns.indexOf(drag.column);
            if (index !== undefined && index !== from && index !== from + 1) {
                columns.splice(from, 1);
                columns.splice(index > from ? index - 1 : index, 0, drag.column);
            }
        }
        this.pushUndo(drag.before);
    }

    /** An element let go over another band moves into it. */
    dropInOtherBand(ev, drag) {
        const target = document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".o_om_rd_dband_body");
        const bandId = target?.dataset.bandId;
        if (!bandId || bandId === drag.band.id) {
            return;
        }
        const band = this.state.layout.bands.find((b) => b.id === bandId);
        const element = drag.element;
        const rect = target.getBoundingClientRect();
        drag.band.elements.splice(drag.band.elements.indexOf(element), 1);
        element.y = this.snap(this.toMm(ev.clientY - rect.top) - drag.grabY);
        this.fitInBand(band, element);
        band.elements.push(element);
        this.state.bandId = band.id;
    }

    moveSelection(drag, dx, dy) {
        const primary = drag.element;
        const origin = drag.origins[primary.id];
        let x = this.snap(origin.x + dx);
        let y = this.snap(origin.y + dy);
        const guides = [];
        const snapped = this.snapToEdges(drag.band, primary, x, y);
        if (snapped.x !== null) {
            x = snapped.x;
            guides.push({ axis: "x", pos: snapped.guideX });
        }
        if (snapped.y !== null) {
            y = snapped.y;
            guides.push({ axis: "y", pos: snapped.guideY });
        }
        const moveX = x - origin.x;
        const moveY = y - origin.y;
        for (const element of this.selectedElements) {
            const start = drag.origins[element.id];
            if (!start) {
                continue;
            }
            element.x = round(Math.max(0, Math.min(start.x + moveX, this.printableWidth - element.w)));
            element.y = round(Math.max(0, start.y + moveY));
        }
        this.state.guides = guides.map((guide) => ({ ...guide, bandId: drag.band.id }));
    }

    /** Edges of the other elements and of the band near the moved element. */
    snapToEdges(band, element, x, y) {
        const limit = SNAP_PX / this.scale;
        const others = band.elements.filter((el) => !this.state.selection.includes(el.id));
        const xs = [0, this.printableWidth / 2, this.printableWidth];
        const ys = [0, band.height / 2, band.height];
        for (const other of others) {
            xs.push(other.x, other.x + other.w / 2, other.x + other.w);
            ys.push(other.y, other.y + other.h / 2, other.y + other.h);
        }
        const best = (targets, start, size) => {
            let result = { value: null, guide: null, distance: limit };
            for (const [offset, edge] of [[0, start], [size / 2, start + size / 2], [size, start + size]]) {
                for (const target of targets) {
                    const distance = Math.abs(target - edge);
                    if (distance < result.distance) {
                        result = { value: round(target - offset), guide: target, distance };
                    }
                }
            }
            return result;
        };
        const bx = best(xs, x, element.w);
        const by = best(ys, y, element.h);
        return { x: bx.value, guideX: bx.guide, y: by.value, guideY: by.guide };
    }

    resizeElement(drag, dx, dy) {
        const { dir, origin, element, band } = drag;
        const line = element.type === "line";
        const snapW = (value) => (line && origin.w < 1 ? round(value, 1) : this.snap(value));
        const snapH = (value) => (line && origin.h < 1 ? round(value, 1) : this.snap(value));
        const min = line ? 0.1 : 2;
        let { x, y, w, h } = origin;
        if (dir.includes("e")) {
            w = snapW(origin.x + origin.w + dx) - origin.x;
        }
        if (dir.includes("s")) {
            h = snapH(origin.y + origin.h + dy) - origin.y;
        }
        if (dir.includes("w")) {
            x = Math.min(this.snap(origin.x + dx), origin.x + origin.w - min);
            w = origin.x + origin.w - x;
        }
        if (dir.includes("n")) {
            y = Math.min(this.snap(origin.y + dy), origin.y + origin.h - min);
            h = origin.y + origin.h - y;
        }
        x = Math.max(0, x);
        y = Math.max(0, y);
        element.x = round(x);
        element.y = round(y);
        element.w = round(Math.max(min, Math.min(w, this.printableWidth - x)));
        element.h = round(Math.max(min, h));
        if (element.y + element.h > band.height) {
            band.height = round(element.y + element.h);
        }
    }

    guideStyle(guide) {
        return guide.axis === "x" ? `left:${this.px(guide.pos)}px` : `top:${this.px(guide.pos)}px`;
    }

    // ------------------------------------------------------------------
    // keyboard
    // ------------------------------------------------------------------

    onKeyDown(ev) {
        if (!this.state.loaded || ev.defaultPrevented) {
            return;
        }
        const target = ev.target;
        const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
        const ctrl = ev.ctrlKey || ev.metaKey;
        const key = ev.key.toLowerCase();
        if (ctrl && key === "s") {
            ev.preventDefault();
            this.save();
            return;
        }
        if (typing || this.state.mode !== "design" || document.querySelector(".modal")) {
            return;
        }
        if (ctrl && key === "z") {
            ev.preventDefault();
            ev.shiftKey ? this.redo() : this.undo();
        } else if (ctrl && key === "y") {
            ev.preventDefault();
            this.redo();
        } else if (ctrl && key === "c") {
            this.copy();
        } else if (ctrl && key === "v") {
            this.paste();
        } else if (ctrl && key === "d") {
            ev.preventDefault();
            this.copy();
            this.paste();
        } else if (key === "delete" || key === "backspace") {
            ev.preventDefault();
            this.deleteSelection();
        } else if (key === "escape") {
            this.clearSelection();
        } else if (key.startsWith("arrow") && this.state.selection.length) {
            ev.preventDefault();
            const step = ev.shiftKey ? 5 : this.state.snap ? this.state.grid : 0.5;
            const [dx, dy] = {
                arrowleft: [-step, 0],
                arrowright: [step, 0],
                arrowup: [0, -step],
                arrowdown: [0, step],
            }[key];
            this.nudge(dx, dy);
        }
    }

    nudge(dx, dy) {
        this.commit(() => {
            for (const element of this.selectedElements) {
                const band = this.bandOf(element.id);
                element.x = round(Math.max(0, Math.min(element.x + dx, this.printableWidth - element.w)));
                element.y = round(Math.max(0, element.y + dy));
                this.fitInBand(band, element);
            }
        });
    }

    copy() {
        const elements = this.selectedElements;
        if (elements.length) {
            this.clipboard = JSON.stringify(elements);
        }
    }

    paste() {
        if (!this.clipboard) {
            return;
        }
        const band = this.selectedBand?.kind !== "table" && this.selectedBand
            || this.bandOf(JSON.parse(this.clipboard)[0].id)
            || this.targetBand();
        if (!band || band.kind === "table") {
            return;
        }
        const elements = JSON.parse(this.clipboard).map((element) => ({
            ...element,
            id: newId("e"),
            x: element.x + 2,
            y: element.y + 2,
        }));
        this.commit(() => {
            for (const element of elements) {
                this.fitInBand(band, element);
                band.elements.push(element);
            }
        });
        this.state.bandId = band.id;
        this.state.selection = elements.map((el) => el.id);
        this.clipboard = JSON.stringify(elements);
    }

    deleteSelection() {
        if (this.state.selection.length) {
            const ids = new Set(this.state.selection);
            this.commit(() => {
                for (const band of this.state.layout.bands) {
                    if (band.elements) {
                        band.elements = band.elements.filter((el) => !ids.has(el.id));
                    }
                }
            });
            this.state.selection = [];
        } else if (this.selectedColumn) {
            this.deleteColumn();
        }
    }

    // ------------------------------------------------------------------
    // inline editing
    // ------------------------------------------------------------------

    startEdit(element) {
        if (this.state.mode !== "design" || !["text", "page"].includes(element.type)) {
            return;
        }
        this.state.editing = { kind: "element", id: element.id, value: element.text || "" };
    }

    startEditColumn(band, column) {
        this.state.bandId = band.id;
        this.state.columnId = column.id;
        this.state.editing = { kind: "column", id: column.id, value: column.label };
    }

    onEditKeyDown(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.state.editing = null;
        } else if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.finishEdit();
        }
    }

    finishEdit() {
        const editing = this.state.editing;
        if (!editing) {
            return;
        }
        this.state.editing = null;
        this.commit(() => {
            if (editing.kind === "column") {
                const column = this.state.layout.bands
                    .flatMap((band) => band.columns || [])
                    .find((col) => col.id === editing.id);
                if (column) {
                    column.label = editing.value;
                }
            } else {
                const element = this.state.layout.bands
                    .flatMap((band) => band.elements || [])
                    .find((el) => el.id === editing.id);
                if (element) {
                    element.text = editing.value;
                }
            }
        });
    }

    // ------------------------------------------------------------------
    // properties
    // ------------------------------------------------------------------

    num(value, fallback = 0) {
        const number = parseFloat(String(value).replace(",", "."));
        return Number.isFinite(number) ? round(number) : fallback;
    }

    setElementProp(key, value) {
        this.commit(() => {
            for (const element of this.selectedElements) {
                element[key] = value;
                if (["x", "y", "w", "h"].includes(key)) {
                    this.fitInBand(this.bandOf(element.id), element);
                }
            }
        });
    }

    setStyle(key, value) {
        this.commit(() => {
            for (const element of this.selectedElements) {
                element.style = { ...defaultStyle(element.style), [key]: value };
            }
        });
    }

    styleOf(key) {
        const element = this.selectedElements[0];
        return element ? defaultStyle(element.style)[key] : undefined;
    }

    setBandProp(key, value) {
        const band = this.selectedBand;
        if (band) {
            this.commit(() => {
                band[key] = value;
            });
        }
    }

    setColumnProp(key, value) {
        const column = this.selectedColumn;
        if (column) {
            this.commit(() => {
                column[key] = value;
            });
        }
    }

    setSetting(key, value) {
        this.state.settings[key] = value;
        this.state.dirty = true;
    }

    alignSelection(how) {
        const elements = this.selectedElements;
        if (elements.length < 2) {
            return;
        }
        const left = Math.min(...elements.map((el) => el.x));
        const right = Math.max(...elements.map((el) => el.x + el.w));
        const top = Math.min(...elements.map((el) => el.y));
        const bottom = Math.max(...elements.map((el) => el.y + el.h));
        const first = elements[0];
        this.commit(() => {
            for (const el of elements) {
                if (how === "left") {
                    el.x = left;
                } else if (how === "right") {
                    el.x = round(right - el.w);
                } else if (how === "center") {
                    el.x = round((left + right) / 2 - el.w / 2);
                } else if (how === "top") {
                    el.y = top;
                } else if (how === "bottom") {
                    el.y = round(bottom - el.h);
                } else if (how === "middle") {
                    el.y = round((top + bottom) / 2 - el.h / 2);
                } else if (how === "width") {
                    el.w = first.w;
                } else if (how === "height") {
                    el.h = first.h;
                }
            }
            if (how === "hspace" || how === "vspace") {
                const horizontal = how === "hspace";
                const sorted = [...elements].sort((a, b) => (horizontal ? a.x - b.x : a.y - b.y));
                const size = sorted.reduce((total, el) => total + (horizontal ? el.w : el.h), 0);
                const gap = ((horizontal ? right - left : bottom - top) - size) / (sorted.length - 1);
                let position = horizontal ? left : top;
                for (const el of sorted) {
                    el[horizontal ? "x" : "y"] = round(position);
                    position += (horizontal ? el.w : el.h) + gap;
                }
            }
        });
    }

    orderSelection(front) {
        const elements = this.selectedElements;
        this.commit(() => {
            for (const element of elements) {
                const band = this.bandOf(element.id);
                band.elements.splice(band.elements.indexOf(element), 1);
                if (front) {
                    band.elements.push(element);
                } else {
                    band.elements.unshift(element);
                }
            }
        });
    }

    deleteColumn() {
        const band = this.selectedBand;
        const column = this.selectedColumn;
        if (column) {
            this.commit(() => band.columns.splice(band.columns.indexOf(column), 1));
            this.state.columnId = null;
        }
    }

    moveColumn(step) {
        const band = this.selectedBand;
        const column = this.selectedColumn;
        const index = band.columns.indexOf(column);
        const to = index + step;
        if (column && to >= 0 && to < band.columns.length) {
            this.commit(() => {
                band.columns.splice(index, 1);
                band.columns.splice(to, 0, column);
            });
        }
    }

    // ------------------------------------------------------------------
    // bands
    // ------------------------------------------------------------------

    get addableBands() {
        const kinds = this.state.layout.bands.map((band) => band.kind);
        return Object.entries(BAND_KINDS)
            .filter(([kind]) => kind !== "table" && !(SINGLE_BANDS.includes(kind) && kinds.includes(kind)))
            .map(([kind, info]) => ({ kind, label: info.label }));
    }

    sortBands() {
        this.state.layout.bands.sort((a, b) => BAND_RANK[a.kind] - BAND_RANK[b.kind]);
    }

    addBand(kind) {
        if (!kind) {
            return;
        }
        const band = { id: newId("b"), kind, height: kind === "record" ? 15 : 10, elements: [] };
        this.commit(() => {
            const bands = this.state.layout.bands;
            const selected = this.selectedBand;
            if (kind === "record" && selected && BAND_RANK[selected.kind] === 2) {
                bands.splice(bands.indexOf(selected) + 1, 0, band);
            } else {
                bands.push(band);
            }
            this.sortBands();
        });
        this.select(band);
    }

    canMoveBand(band, step) {
        const bands = this.state.layout.bands;
        const neighbour = bands[bands.indexOf(band) + step];
        return BAND_RANK[band.kind] === 2 && neighbour && BAND_RANK[neighbour.kind] === 2;
    }

    moveBand(band, step) {
        if (this.canMoveBand(band, step)) {
            const bands = this.state.layout.bands;
            const index = bands.indexOf(band);
            this.commit(() => {
                bands.splice(index, 1);
                bands.splice(index + step, 0, band);
            });
        }
    }

    deleteBand(band) {
        const remove = () => {
            this.commit(() => {
                const bands = this.state.layout.bands;
                bands.splice(bands.indexOf(band), 1);
            });
            this.clearSelection();
        };
        const filled = band.elements?.length || band.columns?.length;
        if (!filled) {
            remove();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete Band"),
            body: _t("Delete the band “%s” and everything on it?", this.bandTitle(band)),
            confirmLabel: _t("Delete"),
            confirm: remove,
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // preview, save, publish
    // ------------------------------------------------------------------

    settingsPayload() {
        const settings = this.state.settings;
        return {
            name: settings.name,
            paper: settings.paper,
            orientation: settings.orientation,
            margin_top: settings.margin_top,
            margin_bottom: settings.margin_bottom,
            margin_left: settings.margin_left,
            margin_right: settings.margin_right,
            page_break: settings.page_break,
        };
    }

    async setMode(mode) {
        this.state.editing = null;
        this.state.mode = mode;
        if (mode === "preview") {
            await this.refreshPreview();
        }
    }

    async refreshPreview() {
        this.state.previewLoading = true;
        try {
            this.state.previewHtml = await this.orm.call(MODEL, "designer_preview", [
                [this.designId],
                this.state.layout,
                this.state.previewRecordId,
                this.settingsPayload(),
            ]);
        } finally {
            this.state.previewLoading = false;
        }
    }

    get previewMarkup() {
        return markup(this.state.previewHtml || "");
    }

    get previewSheetStyle() {
        const settings = this.state.settings;
        return [
            `width:${round(this.pageSize[0])}mm`,
            `padding:${settings.margin_top}mm ${settings.margin_right}mm ${settings.margin_bottom}mm ${settings.margin_left}mm`,
            `zoom:${this.state.zoom}`,
        ].join(";");
    }

    async setPreviewRecord(value) {
        this.state.previewRecordId = parseInt(value) || false;
        await this.refreshPreview();
    }

    async save() {
        if (this.state.saving) {
            return false;
        }
        this.finishEdit();
        this.state.saving = true;
        try {
            const result = await this.orm.call(MODEL, "designer_save", [
                [this.designId],
                this.state.layout,
                this.settingsPayload(),
            ]);
            this.state.layout = result.layout;
            this.state.settings = result.settings;
            this.state.dirty = false;
            this.state.saved = true;
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async publish() {
        if (!(await this.save())) {
            return;
        }
        await this.orm.call(MODEL, "action_publish", [[this.designId]]);
        this.state.settings.state = "published";
        this.notification.add(
            _t("Published: “%(name)s” prints from the Print menu of %(model)s.", {
                name: this.state.settings.name,
                model: this.state.settings.model_name,
            }),
            { type: "success" }
        );
    }

    close() {
        const leave = async () => {
            try {
                await this.action.restore();
            } catch {
                // opened from a link: no previous screen, go to the report
                await this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: MODEL,
                    res_id: this.designId,
                    views: [[false, "form"]],
                });
            }
        };
        if (!this.state.dirty) {
            leave();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved Changes"),
            body: _t("Save the changes to the report before leaving?"),
            confirmLabel: _t("Save"),
            confirm: async () => {
                if (await this.save()) {
                    leave();
                }
            },
            cancelLabel: _t("Discard"),
            cancel: () => {
                this.state.dirty = false;
                leave();
            },
        });
    }

    setZoom(value) {
        this.state.zoom = Math.min(3, Math.max(0.25, round(value)));
    }
}

registry.category("actions").add("om_report_designer", ReportDesigner);
