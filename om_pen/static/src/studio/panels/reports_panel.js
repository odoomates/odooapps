import { Component, onWillStart, proxy, signal, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { studioSections } from "../studio_action";

export const BLOCK_KINDS = [
    { kind: "title", label: _t("Title"), icon: "title" },
    { kind: "text", label: _t("Text"), icon: "subtitles" },
    { kind: "field", label: _t("Field"), icon: "text_fields" },
    { kind: "fields", label: _t("Fields"), icon: "view_list" },
    { kind: "address", label: _t("Address"), icon: "location_on" },
    { kind: "table", label: _t("Table of lines"), icon: "table_chart" },
    { kind: "image", label: _t("Picture"), icon: "image" },
    { kind: "signature", label: _t("Signature"), icon: "edit_square" },
    { kind: "qrcode", label: _t("QR code"), icon: "qr_code" },
    { kind: "barcode", label: _t("Barcode"), icon: "barcode" },
    { kind: "spacer", label: _t("Space"), icon: "height" },
    { kind: "page_break", label: _t("Page break"), icon: "expand_content" },
];

const NEW_BLOCKS = {
    title: { kind: "title", text: _t("Title"), level: 2 },
    text: { kind: "text", text: _t("Some text") },
    field: { kind: "field", field: "" },
    fields: { kind: "fields", fields: [] },
    address: { kind: "address", field: "" },
    table: { kind: "table", lines: "", columns: [] },
    image: { kind: "image", field: "", height: 120 },
    signature: { kind: "signature", field: "", height: 80 },
    qrcode: { kind: "qrcode", field: "" },
    barcode: { kind: "barcode", field: "" },
    spacer: { kind: "spacer", height: 24 },
    page_break: { kind: "page_break" },
};

/** The reports of the model: the ones made here, and the ones of modules to add blocks to. */
export class ReportsPanel extends Component {
    static template = "om_pen.ReportsPanel";
    props = useProps();

    previewRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.BLOCK_KINDS = BLOCK_KINDS;
        this.state = proxy({
            list: null,
            report: null, // the report being designed
            selected: null, // block index
            tab: "blocks",
            preview: "",
            resId: false,
            records: [],
            fields: {}, // model -> fields_get
            saving: false,
            error: "",
        });
        onWillStart(() => this.loadList());
    }

    get model() {
        return this.props.store.info.model;
    }

    async loadList() {
        this.state.list = await this.orm.call("om.pen.studio", "studio_reports", [this.model]);
    }

    async fieldsOf(model) {
        if (!this.state.fields[model]) {
            this.state.fields[model] = await this.orm.call(model, "fields_get", [], {
                attributes: ["string", "type", "relation", "store"],
            });
        }
        return this.state.fields[model];
    }

    // ------------------------------------------------------------------
    // list
    // ------------------------------------------------------------------

    async createReport() {
        const report = await this.orm.call("om.pen.studio", "studio_report_create", [this.model, { name: _t("New Report") }]);
        await this.open(report);
    }

    async extend(standard, position) {
        const report = await this.orm.call("om.pen.studio", "studio_report_create", [
            this.model,
            { inherit_report_id: standard.id, position, name: _t("Blocks on %s", standard.name) },
        ]);
        await this.open(report);
    }

    async openId(id) {
        await this.open(await this.orm.call("om.pen.studio", "studio_report_load", [id]));
    }

    async open(report) {
        await this.fieldsOf(report.model);
        this.state.records = await this.orm.call("om.pen.studio", "studio_report_records", [report.model]);
        this.state.report = report;
        this.state.selected = null;
        this.state.tab = "blocks";
        await this.refreshPreview();
    }

    async back() {
        this.state.report = null;
        await this.loadList();
    }

    deleteReport() {
        const report = this.state.report;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete the report"),
            body: _t("Delete %s? It disappears from the Print menu.", report.name),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.call("om.pen.studio", "studio_report_delete", [report.id]);
                await this.back();
            },
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // designing
    // ------------------------------------------------------------------

    get fields() {
        return this.state.fields[this.state.report?.model] || {};
    }

    fieldList(types, model) {
        const fields = model ? this.state.fields[model] || {} : this.fields;
        return Object.entries(fields)
            .filter(([, f]) => !types || types.includes(f.type))
            .map(([name, f]) => ({ name, string: f.string, type: f.type, relation: f.relation }))
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    get block() {
        const index = this.state.selected;
        return index === null ? null : this.state.report.blocks[index];
    }

    blockLabel(block) {
        const kind = BLOCK_KINDS.find((k) => k.kind === block.kind);
        let detail = block.text || block.label || block.field || block.lines || "";
        if (detail.length > 40) {
            detail = detail.slice(0, 40) + "…";
        }
        return detail ? `${kind?.label}: ${detail}` : kind?.label || block.kind;
    }

    async addBlock(kind) {
        const blocks = this.state.report.blocks;
        const index = this.state.selected === null ? blocks.length : this.state.selected + 1;
        blocks.splice(index, 0, JSON.parse(JSON.stringify(NEW_BLOCKS[kind])));
        this.state.selected = index;
        this.state.tab = "block";
        // a block without its field cannot render yet: save once it is filled in
        if (!["field", "fields", "address", "table", "image", "signature", "qrcode", "barcode"].includes(kind)) {
            await this.save();
        }
    }

    async moveBlock(index, delta) {
        const blocks = this.state.report.blocks;
        const other = index + delta;
        if (other < 0 || other >= blocks.length) {
            return;
        }
        [blocks[index], blocks[other]] = [blocks[other], blocks[index]];
        this.state.selected = other;
        await this.save();
    }

    async removeBlock(index) {
        this.state.report.blocks.splice(index, 1);
        this.state.selected = null;
        await this.save();
    }

    select(index) {
        this.state.selected = index;
        this.state.tab = "block";
        this.markPreview();
    }

    async setBlock(key, value) {
        this.block[key] = value;
        await this.save();
    }

    async onLinesChange(ev) {
        const block = this.block;
        block.lines = ev.target.value;
        block.columns = [];
        const field = this.fields[block.lines];
        if (field?.relation) {
            await this.fieldsOf(field.relation);
        }
    }

    get linesModel() {
        return this.fields[this.block?.lines]?.relation;
    }

    async addColumn(ev) {
        const name = ev.target.value;
        ev.target.value = "";
        if (name) {
            this.block.columns.push({ field: name, total: false });
            await this.save();
        }
    }

    async toggleTotal(column, checked) {
        column.total = checked;
        await this.save();
    }

    async removeColumn(index) {
        this.block.columns.splice(index, 1);
        await this.save();
    }

    async addListField(ev) {
        const name = ev.target.value;
        ev.target.value = "";
        if (name) {
            this.block.fields.push({ field: name });
            await this.save();
        }
    }

    async removeListField(index) {
        this.block.fields.splice(index, 1);
        await this.save();
    }

    insertPlaceholder(ev) {
        const name = ev.target.value;
        ev.target.value = "";
        if (name) {
            this.setBlock("text", `${this.block.text || ""}{{ ${name} }}`);
        }
    }

    async setSetting(key, value) {
        this.state.report[key] = value;
        await this.save();
    }

    async save() {
        const report = this.state.report;
        this.state.saving = true;
        this.state.error = "";
        try {
            const saved = await this.orm.call("om.pen.studio", "studio_report_save", [
                report.id,
                {
                    name: report.name,
                    blocks: report.blocks,
                    layout: report.layout,
                    position: report.position,
                    paperformat_id: report.paperformat_id || false,
                    print_report_name: report.print_report_name,
                    print_menu: report.print_menu,
                },
            ]);
            Object.assign(this.state.report, { ...saved, blocks: this.state.report.blocks });
            await this.refreshPreview();
        } catch (error) {
            this.state.error = error.data?.message || error.message || String(error);
        } finally {
            this.state.saving = false;
        }
    }

    async refreshPreview() {
        const result = await this.orm.call("om.pen.studio", "studio_report_preview", [
            this.state.report.id,
            this.state.resId || false,
        ]);
        this.state.resId = result.res_id;
        this.state.preview = result.html;
    }

    async onRecordChange(ev) {
        this.state.resId = Number(ev.target.value) || false;
        await this.refreshPreview();
    }

    /** Clicking a block in the preview selects it in the panel. */
    onPreviewLoad() {
        const frame = this.previewRef();
        const doc = frame?.contentDocument;
        if (!doc) {
            return;
        }
        const style = doc.createElement("style");
        style.textContent = `
            [data-pen-block] { cursor: pointer; outline: 1px dashed transparent; outline-offset: 3px; }
            [data-pen-block]:hover { outline-color: #1f9d93; }
            [data-pen-block].o_pen_block_selected { outline: 2px solid #5b2b5e; }
            a { pointer-events: none; }`;
        doc.head.appendChild(style);
        doc.addEventListener("click", (ev) => {
            ev.preventDefault();
            const block = ev.target.closest("[data-pen-block]");
            if (block) {
                this.select(Number(block.dataset.penBlock));
            }
        });
        this.markPreview();
    }

    markPreview() {
        const doc = this.previewRef()?.contentDocument;
        if (!doc) {
            return;
        }
        for (const el of doc.querySelectorAll("[data-pen-block]")) {
            el.classList.toggle("o_pen_block_selected", Number(el.dataset.penBlock) === this.state.selected);
        }
    }

    get pdfUrl() {
        const report = this.state.report;
        return report?.report_name && this.state.resId ? `/report/pdf/${report.report_name}/${this.state.resId}` : false;
    }
}

studioSections.add("reports", { label: _t("Reports"), Component: ReportsPanel }, { sequence: 30 });
