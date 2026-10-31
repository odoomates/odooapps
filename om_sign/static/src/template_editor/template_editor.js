import {
    Component,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    proxy,
    signal,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "sign.template";
const WORKER = "/web/static/lib/pdfjs/build/pdf.worker.js";
// the colours of the roles: the colour indexes of Odoo
export const COLORS = [
    "#9ca3af", "#f06050", "#f4a460", "#f7cd1f", "#6cc1ed", "#814968",
    "#eb7e7f", "#2c8397", "#475577", "#d6145f", "#30c381", "#9365b8",
];
// the size of a new field, in points of the page
const SIZES = {
    signature: [170, 50],
    initials: [70, 36],
    name: [170, 20],
    email: [190, 20],
    company: [170, 20],
    date: [90, 20],
    text: [190, 20],
    checkbox: [16, 16],
};
const ICONS = {
    signature: "edit",
    initials: "edit_square",
    name: "badge",
    email: "mail",
    company: "business",
    date: "calendar_today",
    text: "text_fields",
    checkbox: "check_box",
};
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];
// pdf.js shows a page at 100% with 96 pixels to the inch of 72 points
const PDF_TO_CSS = 96 / 72;
const MIN_SIZE = 6; // points
const DRAG_THRESHOLD = 4; // pixels

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Sharing the template by a public link: on or off, the link to copy, a new link replacing the one given.
 */
export class SignShareDialog extends Component {
    static template = "om_sign.ShareDialog";
    static components = { Dialog };
    props = useProps({
        templateId: t.number(),
        share: t.object(),
        canEdit: t.boolean(),
        onChange: t.function(),
        close: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ ...this.props.share, busy: false });
    }

    async update(params) {
        this.state.busy = true;
        try {
            const share = await this.orm.call(MODEL, "editor_share", [this.props.templateId], params);
            Object.assign(this.state, share);
            this.props.onChange(share);
        } finally {
            this.state.busy = false;
        }
    }

    onToggle(ev) {
        this.update({ enabled: ev.target.checked });
    }

    async copy() {
        await browser.navigator.clipboard.writeText(this.state.url);
        this.notification.add(_t("Link copied."), { type: "success" });
    }
}

/**
 * The editor of a sign template: the pages of its PDF, the fields of each role placed on them. A field is added
 * from the palette, by dragging it onto a page or by a click (on the page in view); it is moved and resized with
 * the mouse, and edited in the side panel once selected. The places are kept as fractions of the page as shown,
 * from its top left corner: the zoom changes nothing of them.
 */
export class SignTemplateEditor extends Component {
    static template = "om_sign.TemplateEditor";
    static components = { RecordSelector };
    props = useProps({ ...standardActionServiceProps });

    root = signal.ref();
    scroller = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        const params = this.props.action.params || {};
        const context = this.props.action.context || {};
        this.templateId = params.template_id || context.active_id || false;
        this.state = proxy({
            loaded: false,
            pdfError: false,
            template: null,
            share: {},
            roles: [],
            fields: [],
            types: [],
            signerTypes: [],
            canEdit: false,
            pages: [],
            zoom: 1,
            selectedId: false,
            roleId: false,
            dirty: false,
            saving: false,
            ghost: null,
        });
        this.pdf = null;
        this.drag = null;
        this.newId = 0;
        this.renderTasks = new Map();
        onWillStart(() => this.load());
        onMounted(() => this.renderPages());
        onPatched(() => this.renderPages());
        onWillUnmount(() => {
            for (const task of this.renderTasks.values()) {
                task.cancel();
            }
            this.pdf?.destroy();
        });
        useListener(window, "pointermove", (ev) => this.onPointerMove(ev));
        useListener(window, "pointerup", (ev) => this.onPointerUp(ev));
        useHotkey("delete", () => this.removeSelected());
        useHotkey("backspace", () => this.removeSelected());
        useHotkey("escape", () => this.select(false));
    }

    async load() {
        if (!this.templateId) {
            this.state.loaded = true;
            return;
        }
        const [data] = await Promise.all([
            this.orm.call(MODEL, "editor_load", [this.templateId]),
            this.loadPdfjs(),
        ]);
        this.apply(data);
        await this.loadPdf();
        this.state.loaded = true;
    }

    async loadPdfjs() {
        try {
            await loadPDFJSAssets();
            if (!globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc) {
                globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc = WORKER;
            }
        } catch {
            this.state.pdfError = true;
        }
    }

    async loadPdf() {
        if (this.state.pdfError) {
            return;
        }
        try {
            this.pdf = await globalThis.pdfjsLib.getDocument({ url: this.state.template.pdf_url }).promise;
            const pages = [];
            for (let number = 1; number <= this.pdf.numPages; number++) {
                const page = await this.pdf.getPage(number);
                // as shown: the visible box of the page, turned by its rotation
                const { width, height } = page.getViewport({ scale: 1 });
                pages.push({ number, width, height });
            }
            this.state.pages = pages;
        } catch {
            this.state.pdfError = true;
        }
    }

    apply(data) {
        this.state.template = data.template;
        this.state.share = data.share;
        this.state.types = data.types;
        this.state.signerTypes = data.signer_types;
        this.state.canEdit = data.can_edit;
        // the order of signing as 1, 2, 3...: the roles of the same sequence keep one number
        const sequences = [...new Set(data.roles.map((role) => role.sequence))].sort((a, b) => a - b);
        this.state.roles = data.roles.map((role) => ({ ...role, sequence: sequences.indexOf(role.sequence) + 1 }));
        this.state.fields = data.fields.map((field) => ({ ...field }));
        if (!this.state.roles.length) {
            this.state.roles.push(this.makeRole(_t("Customer")));
        }
        if (!this.state.roles.some((role) => role.id === this.state.roleId)) {
            this.state.roleId = this.state.roles[0].id;
        }
        if (!this.state.fields.some((field) => field.id === this.state.selectedId)) {
            this.state.selectedId = false;
        }
        this.state.dirty = false;
    }

    // ------------------------------------------------------------------
    // Rendering the pages
    // ------------------------------------------------------------------

    pageWidth(page) {
        return Math.round(page.width * PDF_TO_CSS * this.state.zoom);
    }

    pageStyle(page) {
        const width = this.pageWidth(page);
        return `width: ${width}px; height: ${Math.round((width * page.height) / page.width)}px;`;
    }

    renderPages() {
        if (!this.pdf || !this.root()) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        for (const canvas of this.root().querySelectorAll("canvas.o_sign_page_canvas")) {
            const number = parseInt(canvas.dataset.page, 10);
            const key = `${this.state.zoom}:${ratio}`;
            if (canvas.dataset.rendered === key) {
                continue;
            }
            canvas.dataset.rendered = key;
            this.renderPage(canvas, number, ratio);
        }
    }

    async renderPage(canvas, number, ratio) {
        this.renderTasks.get(number)?.cancel();
        const page = await this.pdf.getPage(number);
        const viewport = page.getViewport({ scale: PDF_TO_CSS * this.state.zoom * ratio });
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const task = page.render({ canvasContext: canvas.getContext("2d"), viewport });
        this.renderTasks.set(number, task);
        try {
            await task.promise;
        } catch (error) {
            if (error?.name !== "RenderingCancelledException") {
                throw error;
            }
        } finally {
            if (this.renderTasks.get(number) === task) {
                this.renderTasks.delete(number);
            }
        }
    }

    setZoom(zoom) {
        this.state.zoom = zoom;
    }

    zoomBy(step) {
        const index = ZOOMS.indexOf(this.state.zoom);
        this.state.zoom = ZOOMS[clamp(index + step, 0, ZOOMS.length - 1)];
    }

    get zoomLabel() {
        return `${Math.round(this.state.zoom * 100)}%`;
    }

    get canZoomIn() {
        return this.state.zoom < ZOOMS[ZOOMS.length - 1];
    }

    get canZoomOut() {
        return this.state.zoom > ZOOMS[0];
    }

    // ------------------------------------------------------------------
    // Reading
    // ------------------------------------------------------------------

    get selected() {
        return this.state.fields.find((field) => field.id === this.state.selectedId) || null;
    }

    get activeRole() {
        return this.role(this.state.roleId);
    }

    get rolesBySequence() {
        return [...this.state.roles].sort((a, b) => a.sequence - b.sequence);
    }

    role(roleId) {
        return this.state.roles.find((role) => role.id === roleId) || null;
    }

    roleColor(role) {
        return COLORS[(role?.color || 0) % COLORS.length];
    }

    roleFieldCount(role) {
        return this.state.fields.filter((field) => field.role_id === role.id).length;
    }

    fieldsOf(page) {
        return this.state.fields.filter((field) => field.page === page.number);
    }

    typeLabel(type) {
        return (this.state.types.find(([key]) => key === type) || [type, type])[1];
    }

    icon(type) {
        return ICONS[type] || "text_fields";
    }

    fieldText(field) {
        return field.label || this.typeLabel(field.type);
    }

    fieldStyle(field) {
        const color = this.roleColor(this.role(field.role_id));
        return [
            `left: ${field.pos_x * 100}%`,
            `top: ${field.pos_y * 100}%`,
            `width: ${field.width * 100}%`,
            `height: ${field.height * 100}%`,
            `--o-sign-role-color: ${color}`,
        ].join("; ");
    }

    fieldClass(field) {
        return {
            o_sign_field_selected: field.id === this.state.selectedId,
            o_sign_field_small: field.type === "checkbox",
            o_sign_field_readonly: !this.state.canEdit,
        };
    }

    get pageCount() {
        return this.state.pages.length || this.state.template?.page_count || 0;
    }

    // ------------------------------------------------------------------
    // Fields
    // ------------------------------------------------------------------

    changed() {
        this.state.dirty = true;
    }

    select(fieldId) {
        this.state.selectedId = fieldId;
        const field = this.selected;
        if (field) {
            this.state.roleId = field.role_id;
        }
    }

    /** A new field of `type` for the active role, its center at (`x`, `y`), fractions of `page`. */
    addField(type, page, x, y) {
        const [width, height] = SIZES[type] || SIZES.text;
        const fieldWidth = Math.min(width / page.width, 1);
        const fieldHeight = Math.min(height / page.height, 1);
        const field = {
            id: `new_${++this.newId}`,
            role_id: this.state.roleId,
            type,
            page: page.number,
            pos_x: clamp(x - fieldWidth / 2, 0, 1 - fieldWidth),
            pos_y: clamp(y - fieldHeight / 2, 0, 1 - fieldHeight),
            width: fieldWidth,
            height: fieldHeight,
            required: type !== "checkbox",
            label: "",
        };
        this.state.fields.push(field);
        this.state.selectedId = field.id;
        this.changed();
        return field;
    }

    /** A click on the palette: the field goes in the middle of the page in view. */
    addToVisiblePage(type) {
        const page = this.pageInView();
        if (page) {
            this.addField(type, page, 0.5, 0.5);
        }
    }

    pageInView() {
        const scroller = this.scroller();
        if (!scroller || !this.state.pages.length) {
            return null;
        }
        const area = scroller.getBoundingClientRect();
        const middle = area.top + area.height / 2;
        for (const element of scroller.querySelectorAll(".o_sign_page")) {
            const rect = element.getBoundingClientRect();
            if (rect.bottom >= middle || rect.bottom >= area.bottom) {
                return this.state.pages[parseInt(element.dataset.page, 10) - 1];
            }
        }
        return this.state.pages[this.state.pages.length - 1];
    }

    removeField(field) {
        this.state.fields = this.state.fields.filter((other) => other.id !== field.id);
        if (this.state.selectedId === field.id) {
            this.state.selectedId = false;
        }
        this.changed();
    }

    removeSelected() {
        if (this.selected && this.state.canEdit) {
            this.removeField(this.selected);
        }
    }

    setField(field, name, value) {
        field[name] = value;
        this.changed();
    }

    setFieldRole(field, value) {
        const role = this.state.roles.find((other) => String(other.id) === value);
        if (role) {
            this.state.roleId = role.id;
            this.setField(field, "role_id", role.id);
        }
    }

    percent(value) {
        return `${Math.round(value * 100)}%`;
    }

    // ------------------------------------------------------------------
    // The mouse: adding from the palette, moving and resizing
    // ------------------------------------------------------------------

    pageAt(clientX, clientY) {
        for (const element of this.root().querySelectorAll(".o_sign_page")) {
            const rect = element.getBoundingClientRect();
            if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                return { page: this.state.pages[parseInt(element.dataset.page, 10) - 1], rect };
            }
        }
        return null;
    }

    pageRect(number) {
        return this.root().querySelector(`.o_sign_page[data-page="${number}"]`).getBoundingClientRect();
    }

    startNew(ev, type) {
        if (!this.state.canEdit || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        this.drag = { mode: "new", type, startX: ev.clientX, startY: ev.clientY, moved: false };
    }

    startMove(ev, field) {
        if (ev.button !== 0) {
            return;
        }
        this.select(field.id);
        if (!this.state.canEdit) {
            return;
        }
        ev.preventDefault();
        const rect = this.pageRect(field.page);
        this.drag = {
            mode: "move",
            field,
            startX: ev.clientX,
            startY: ev.clientY,
            // where the field was grabbed, in pixels from its top left corner
            grabX: ev.clientX - (rect.left + field.pos_x * rect.width),
            grabY: ev.clientY - (rect.top + field.pos_y * rect.height),
            moved: false,
        };
    }

    startResize(ev, field) {
        if (ev.button !== 0 || !this.state.canEdit) {
            return;
        }
        ev.preventDefault();
        this.select(field.id);
        this.drag = {
            mode: "resize",
            field,
            startX: ev.clientX,
            startY: ev.clientY,
            width: field.width,
            height: field.height,
            rect: this.pageRect(field.page),
            moved: false,
        };
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        const distance = Math.abs(ev.clientX - drag.startX) + Math.abs(ev.clientY - drag.startY);
        if (!drag.moved && distance < DRAG_THRESHOLD) {
            return;
        }
        drag.moved = true;
        if (drag.mode === "new") {
            this.state.ghost = { type: drag.type, x: ev.clientX, y: ev.clientY };
        } else if (drag.mode === "move") {
            this.moveTo(drag, ev.clientX, ev.clientY);
        } else if (drag.mode === "resize") {
            const { field, rect } = drag;
            const page = this.state.pages[field.page - 1];
            field.width = clamp(drag.width + (ev.clientX - drag.startX) / rect.width, MIN_SIZE / page.width,
                1 - field.pos_x);
            field.height = clamp(drag.height + (ev.clientY - drag.startY) / rect.height, MIN_SIZE / page.height,
                1 - field.pos_y);
            this.changed();
        }
    }

    /** The field follows the mouse, onto another page too. */
    moveTo(drag, clientX, clientY) {
        const { field } = drag;
        const target = this.pageAt(clientX, clientY);
        if (target && target.page.number !== field.page) {
            // the same size in points on the other page
            const from = this.state.pages[field.page - 1];
            field.width = Math.min((field.width * from.width) / target.page.width, 1);
            field.height = Math.min((field.height * from.height) / target.page.height, 1);
            field.page = target.page.number;
        }
        const rect = target && target.page.number === field.page ? target.rect : this.pageRect(field.page);
        field.pos_x = clamp((clientX - drag.grabX - rect.left) / rect.width, 0, 1 - field.width);
        field.pos_y = clamp((clientY - drag.grabY - rect.top) / rect.height, 0, 1 - field.height);
        this.changed();
    }

    onPointerUp(ev) {
        const drag = this.drag;
        this.drag = null;
        if (!drag) {
            return;
        }
        if (drag.mode === "new") {
            this.state.ghost = null;
            if (!drag.moved) {
                this.addToVisiblePage(drag.type);
                return;
            }
            const target = this.pageAt(ev.clientX, ev.clientY);
            if (target) {
                this.addField(
                    drag.type,
                    target.page,
                    (ev.clientX - target.rect.left) / target.rect.width,
                    (ev.clientY - target.rect.top) / target.rect.height
                );
            }
        }
    }

    onCanvasPointerDown(ev) {
        if (!ev.target.closest(".o_sign_field")) {
            this.select(false);
        }
    }

    get ghostStyle() {
        const { x, y } = this.state.ghost;
        return `left: ${x}px; top: ${y}px; --o-sign-role-color: ${this.roleColor(this.activeRole)};`;
    }

    // ------------------------------------------------------------------
    // Roles
    // ------------------------------------------------------------------

    makeRole(name) {
        const used = new Set(this.state.roles.map((role) => role.color));
        const color = [1, 4, 10, 2, 11, 7, 9, 3, 5, 8, 6].find((index) => !used.has(index)) || 1;
        const sequence = Math.max(0, ...this.state.roles.map((role) => role.sequence)) + 1;
        return { id: `new_${++this.newId}`, name, sequence, color, signer_type: "choose", partner_id: false };
    }

    addRole() {
        const role = this.makeRole(_t("Signer %s", this.state.roles.length + 1));
        this.state.roles.push(role);
        this.state.roleId = role.id;
        this.changed();
    }

    chooseRole(role) {
        this.state.roleId = role.id;
        if (this.selected && this.state.canEdit) {
            this.setField(this.selected, "role_id", role.id);
        }
    }

    setRole(role, name, value) {
        role[name] = value;
        if (name === "signer_type" && value !== "partner") {
            role.partner_id = false;
        }
        this.changed();
    }

    setSequence(role, value) {
        const sequence = parseInt(value, 10);
        role.sequence = Number.isNaN(sequence) ? role.sequence : Math.max(1, sequence);
        this.changed();
    }

    nextColor(role) {
        role.color = (role.color % (COLORS.length - 1)) + 1;
        this.changed();
    }

    /** Swap the place in the order of signing with the role before or after. */
    moveRole(role, delta) {
        const roles = this.rolesBySequence;
        const other = roles[roles.indexOf(role) + delta];
        if (!other) {
            return;
        }
        if (other.sequence !== role.sequence) {
            [role.sequence, other.sequence] = [other.sequence, role.sequence];
        } else {
            // it signed together with the other: it now signs alone, before or after it
            const sequence = role.sequence;
            for (const next of roles) {
                if (next !== role && (delta > 0 ? next.sequence > sequence : next.sequence >= sequence)) {
                    next.sequence += 1;
                }
            }
            if (delta > 0) {
                role.sequence += 1;
            }
        }
        this.changed();
    }

    removeRole(role) {
        if (this.state.roles.length === 1) {
            this.notification.add(_t("A template has a role signing it at least."), { type: "warning" });
            return;
        }
        const remove = () => {
            this.state.fields = this.state.fields.filter((field) => field.role_id !== role.id);
            this.state.roles = this.state.roles.filter((other) => other.id !== role.id);
            if (this.state.roleId === role.id) {
                this.state.roleId = this.state.roles[0].id;
            }
            if (this.state.selectedId && !this.selected) {
                this.state.selectedId = false;
            }
            this.changed();
        };
        const count = this.roleFieldCount(role);
        if (!count) {
            remove();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete the Role"),
            body: _t("The %(count)s fields of %(role)s are deleted with it.", { count, role: role.name }),
            confirmLabel: _t("Delete"),
            confirm: remove,
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // Saving and leaving
    // ------------------------------------------------------------------

    problems() {
        const problems = [];
        for (const role of this.state.roles) {
            if (!(role.name || "").trim()) {
                problems.push(_t("Name every role."));
            }
            if (role.signer_type === "partner" && !role.partner_id) {
                problems.push(_t("Choose the contact signing as %s.", role.name));
            }
        }
        return problems;
    }

    async save() {
        if (this.state.saving) {
            return false;
        }
        const problems = this.problems();
        if (problems.length) {
            this.notification.add(problems[0], { type: "danger" });
            return false;
        }
        this.state.saving = true;
        try {
            const data = {
                roles: this.state.roles.map((role) => ({ ...role })),
                fields: this.state.fields.map((field) => ({ ...field })),
            };
            const selectedIndex = this.state.fields.findIndex((field) => field.id === this.state.selectedId);
            const roleIndex = this.state.roles.findIndex((role) => role.id === this.state.roleId);
            const result = await this.orm.call(MODEL, "editor_save", [this.templateId, data]);
            // the records keep their order: the new ids are found at the same place
            this.state.selectedId = result.fields[selectedIndex]?.id || false;
            this.state.roleId = result.roles[roleIndex]?.id || false;
            this.apply(result);
            this.notification.add(_t("Saved."), { type: "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async send(method = "action_send") {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        const action = await this.orm.call(MODEL, method, [[this.templateId]]);
        await this.action.doAction(action);
    }

    sendBulk() {
        return this.send("action_send_bulk");
    }

    async share() {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        this.dialog.add(SignShareDialog, {
            templateId: this.templateId,
            share: { ...this.state.share },
            canEdit: this.state.canEdit,
            onChange: (share) => (this.state.share = share),
        });
    }

    openForm() {
        this.leave(() =>
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: MODEL,
                res_id: this.templateId,
                views: [[false, "form"]],
            })
        );
    }

    close() {
        this.leave(() => this.action.doAction("om_sign.sign_template_action", { clearBreadcrumbs: true }));
    }

    leave(callback) {
        if (!this.state.dirty) {
            callback();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved Changes"),
            body: _t("Save the changes to the template before leaving?"),
            confirmLabel: _t("Save"),
            confirm: async () => {
                if (await this.save()) {
                    callback();
                }
            },
            cancelLabel: _t("Discard"),
            cancel: () => {
                this.state.dirty = false;
                callback();
            },
        });
    }
}

registry.category("actions").add("om_sign_template_editor", SignTemplateEditor);
