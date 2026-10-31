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
import { Dialog } from "@web/core/dialog/dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { NameAndSignature } from "@web/core/signature/name_and_signature";
import { useService } from "@web/core/utils/hooks";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { debounce } from "@web/core/utils/timing";
import { redirect } from "@web/core/utils/urls";

const WORKER = "/web/static/lib/pdfjs/build/pdf.worker.js";
// pdf.js shows a page at 100% with 96 pixels to the inch of 72 points
const PDF_TO_CSS = 96 / 72;
// the size of the pages, in points, when the PDF cannot be shown: A4
const BLANK_PAGE = { width: 595, height: 842 };
const IMAGE_TYPES = ["signature", "initials"];
// filled for the signer, not changed by them
const READONLY_TYPES = ["email", "date"];
// the text of a field, as a part of the height of its box
const FONT_RATIO = 0.62;
const TEXT_LIMIT = 1000;

function typeLabels() {
    return {
        signature: _t("Signature"),
        initials: _t("Initials"),
        name: _t("Name"),
        email: _t("Email"),
        company: _t("Company"),
        date: _t("Date"),
        text: _t("Text"),
        checkbox: _t("Checkbox"),
    };
}

/** The signature pad of the portal, its modes named Type, Draw and Upload. */
export class SignNameAndSignature extends NameAndSignature {
    static template = "om_sign.NameAndSignature";
}

/**
 * The signature or the initials of the signer: drawn, typed in a script font or loaded from an image, as the
 * signature of the portal is.
 */
export class SignFieldDialog extends Component {
    static template = "om_sign.SignFieldDialog";
    static components = { Dialog, SignNameAndSignature };
    props = useProps({
        type: t.string(),
        name: t.string().optional(""),
        onAdopt: t.function(),
        onClear: t.function().optional(),
        close: t.function(),
    });

    setup() {
        this.ui = useService("ui");
        this.signature = proxy({ name: this.props.name, isSignatureEmpty: true });
    }

    get isInitials() {
        return this.props.type === "initials";
    }

    get title() {
        return this.isInitials ? _t("Adopt Your Initials") : _t("Adopt Your Signature");
    }

    get nameAndSignatureProps() {
        return {
            signature: this.signature,
            signatureType: this.isInitials ? "initial" : "signature",
            displaySignatureRatio: this.isInitials ? 2 : 3,
        };
    }

    adopt() {
        if (this.signature.isSignatureEmpty) {
            return;
        }
        this.props.onAdopt({
            name: (this.signature.name || "").trim(),
            image: this.signature.getSignatureImage(),
        });
        this.props.close();
    }

    clear() {
        this.props.onClear();
        this.props.close();
    }
}

/** Declining to sign, with the reason, posted as the page did before. */
export class SignDeclineDialog extends Component {
    static template = "om_sign.SignDeclineDialog";
    static components = { Dialog };
    props = useProps({
        action: t.string(),
        close: t.function(),
    });

    setup() {
        this.ui = useService("ui");
        this.csrfToken = odoo.csrf_token;
    }
}

/**
 * The signing page of a request of a template: the pages of the document, the fields of the signer on them where
 * they are filled in, the fields the others filled already shown as they are. A bar on top leads from one field
 * to the next, the required ones first, and signs once they are all filled.
 *
 * The places of the fields are fractions of their page as pdf.js shows it, from its top left corner: the pages
 * fit the width of the screen and the fields follow.
 */
export class SigningPage extends Component {
    static template = "om_sign.SigningPage";
    static components = { Dropdown, DropdownItem };
    props = useProps({
        baseUrl: t.string(),
        documentName: t.string(),
        companyName: t.string().optional(""),
        companyId: t.number().optional(0),
        reference: t.string().optional(""),
        message: t.string().optional(""),
        signerName: t.string().optional(""),
        // the document with the fields filled so far, nothing to fill: signed, waiting or for a copy
        readonly: t.boolean().optional(false),
    });

    root = signal.ref();

    setup() {
        this.dialog = useService("dialog");
        this.labels = typeLabels();
        this.state = proxy({
            loaded: false,
            loadError: false,
            stale: false,
            pdfError: false,
            pages: [],
            fields: [],
            others: [],
            values: {},
            activeId: false,
            started: false,
            adopted: { signature: false, initials: false },
            signedName: "",
            submitting: false,
            signed: false,
            error: false,
            status: false,
            signedCount: 0,
            signerCount: 0,
        });
        this.pdf = null;
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
        useListener(window, "resize", debounce(() => this.renderPages(), 150));
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    async load() {
        let data;
        try {
            [data] = await Promise.all([rpc(`${this.props.baseUrl}/fields`), this.loadPdfjs()]);
        } catch {
            this.state.loadError = true;
            this.state.loaded = true;
            return;
        }
        if (this.props.readonly) {
            this.state.status = data.status || false;
            this.state.signedCount = data.signed_count || 0;
            this.state.signerCount = data.signer_count || 0;
            this.state.fields = [];
            this.state.others = data.shown || [];
            await this.loadPdf(data.document_url, data.page_count);
            this.state.loaded = true;
            return;
        }
        // signed, declined or a code to enter since the page was opened: the server shows what to do
        this.state.stale = !data.can_sign || data.needs_code;
        this.state.fields = data.fields;
        this.state.others = data.others || [];
        for (const field of data.fields) {
            this.state.values[field.id] = this.initialValue(field);
        }
        await this.loadPdf(data.document_url, data.page_count);
        this.state.loaded = true;
    }

    initialValue(field) {
        if (field.type === "checkbox") {
            return Boolean(field.value);
        }
        if (IMAGE_TYPES.includes(field.type)) {
            return false;
        }
        return field.value || field.default || "";
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

    async loadPdf(url, pageCount) {
        if (!this.state.pdfError) {
            try {
                this.pdf = await globalThis.pdfjsLib.getDocument({ url }).promise;
                const pages = [];
                for (let number = 1; number <= this.pdf.numPages; number++) {
                    const page = await this.pdf.getPage(number);
                    const { width, height } = page.getViewport({ scale: 1 });
                    pages.push({ number, width, height });
                }
                this.state.pages = pages;
                return;
            } catch {
                this.pdf = null;
                this.state.pdfError = true;
            }
        }
        // the fields are still filled in, on blank pages
        const count = Math.max(pageCount || 0, ...this.state.fields.map((field) => field.page), 1);
        this.state.pages = Array.from({ length: count }, (_, index) => ({ number: index + 1, ...BLANK_PAGE }));
    }

    // ------------------------------------------------------------------
    // Rendering the pages
    // ------------------------------------------------------------------

    pageStyle(page) {
        return [
            `max-width: ${Math.round(page.width * PDF_TO_CSS)}px`,
            `aspect-ratio: ${page.width} / ${page.height}`,
        ].join("; ");
    }

    /** Each page is drawn at the width it is shown, sharp on the screen; again when that width changes. */
    renderPages() {
        if (!this.pdf || !this.root()) {
            return;
        }
        const ratio = window.devicePixelRatio || 1;
        for (const canvas of this.root().querySelectorAll("canvas.o_sign_signing_canvas")) {
            const width = Math.round(canvas.parentElement.clientWidth * ratio);
            if (!width || canvas.dataset.rendered === String(width)) {
                continue;
            }
            canvas.dataset.rendered = String(width);
            this.renderPage(canvas, parseInt(canvas.dataset.page, 10), width);
        }
    }

    async renderPage(canvas, number, width) {
        this.renderTasks.get(number)?.cancel();
        const page = await this.pdf.getPage(number);
        const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width });
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

    // ------------------------------------------------------------------
    // Reading
    // ------------------------------------------------------------------

    fieldsOf(page) {
        return this.state.fields.filter((field) => field.page === page.number);
    }

    othersOf(page) {
        return this.state.others.filter((field) => field.page === page.number);
    }

    boxStyle(field, page) {
        // the text takes a part of the height of the box, the page being as wide as its container
        const fontSize = field.height * (page.height / page.width) * 100 * FONT_RATIO;
        return [
            `left: ${field.pos_x * 100}%`,
            `top: ${field.pos_y * 100}%`,
            `width: ${field.width * 100}%`,
            `height: ${field.height * 100}%`,
            `font-size: max(9px, ${fontSize.toFixed(3)}cqw)`,
        ].join("; ");
    }

    fieldClass(field) {
        return {
            o_sign_signing_field_empty: !this.isFilled(field),
            o_sign_signing_field_active: field.id === this.state.activeId,
            o_sign_signing_field_required: field.required,
            o_sign_signing_field_readonly: this.isReadonly(field),
        };
    }

    label(field) {
        return field.label || this.labels[field.type] || field.type;
    }

    ariaLabel(field) {
        const label = this.label(field);
        return field.required ? _t("%s (required)", label) : label;
    }

    isImage(field) {
        return IMAGE_TYPES.includes(field.type);
    }

    isReadonly(field) {
        return READONLY_TYPES.includes(field.type);
    }

    value(field) {
        return this.state.values[field.id];
    }

    displayDate(value) {
        const date = value && deserializeDate(value);
        return date && date.isValid ? formatDate(date) : value || "";
    }

    isFilled(field) {
        const value = this.value(field);
        if (field.type === "checkbox") {
            return value === true;
        }
        if (this.isImage(field)) {
            return Boolean(value);
        }
        return Boolean((value || "").trim());
    }

    get requiredFields() {
        return this.state.fields.filter((field) => field.required);
    }

    get toFill() {
        return this.requiredFields.filter((field) => !this.isFilled(field));
    }

    get progressText() {
        const total = this.requiredFields.length;
        return _t("%(done)s of %(total)s done", { done: total - this.toFill.length, total });
    }

    get progressPercent() {
        const total = this.requiredFields.length;
        return total ? Math.round(((total - this.toFill.length) * 100) / total) : 100;
    }

    get canFinish() {
        return !this.toFill.length && !this.state.submitting && !this.state.signed;
    }

    /** :return: the next field to fill after the active one: a required one, else one left empty */
    get nextField() {
        const fields = this.state.fields;
        let pending = this.toFill;
        if (!pending.length) {
            pending = fields.filter(
                (field) => !this.isFilled(field) && !this.isReadonly(field) && field.type !== "checkbox"
            );
        }
        if (!pending.length) {
            return null;
        }
        const index = fields.findIndex((field) => field.id === this.state.activeId);
        return pending.find((field) => fields.indexOf(field) > index) || pending[0];
    }

    get nextLabel() {
        return this.state.started ? _t("Next") : _t("Start");
    }

    get finishTitle() {
        return this.toFill.length ? _t("Fill in the required fields first") : _t("Sign the document");
    }

    pageLabel(page) {
        return _t("Page %(page)s of %(count)s", { page: page.number, count: this.state.pages.length });
    }

    get downloadUrl() {
        return `${this.props.baseUrl}/document?download=1`;
    }

    get isCompleted() {
        return ["completed", "copy_completed"].includes(this.state.status);
    }

    get statusBadge() {
        if (this.isCompleted) {
            return _t("Signed");
        }
        if (this.state.status === "copy_closed") {
            return _t("Closed");
        }
        return _t("%(signed)s of %(total)s signed", {
            signed: this.state.signedCount,
            total: this.state.signerCount,
        });
    }

    get subtitle() {
        return [this.props.companyName, this.props.reference].filter(Boolean).join(" · ");
    }

    get logoUrl() {
        return this.props.companyId ? `/logo.png?company=${this.props.companyId}` : "";
    }

    get defaultName() {
        const name = this.state.fields.find((field) => field.type === "name" && this.isFilled(field));
        return this.state.signedName || (name ? this.value(name).trim() : this.props.signerName);
    }

    // ------------------------------------------------------------------
    // Filling
    // ------------------------------------------------------------------

    activate(field) {
        this.state.activeId = field.id;
        this.state.started = true;
    }

    targetOf(field) {
        return this.root()?.querySelector(`.o_sign_signing_field[data-id="${field.id}"] .o_sign_signing_target`);
    }

    focusField(field) {
        this.activate(field);
        const target = this.targetOf(field);
        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.focus({ preventScroll: true });
        }
    }

    goNext() {
        const field = this.nextField;
        if (field) {
            this.focusField(field);
        } else {
            this.root()?.querySelector(".o_sign_signing_finish")?.focus();
        }
    }

    onInput(field, ev) {
        this.state.values[field.id] = ev.target.value;
        this.state.error = false;
    }

    onKeydownInput(field, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.goNext();
        }
    }

    toggle(field) {
        this.activate(field);
        this.state.values[field.id] = !this.value(field);
        this.state.error = false;
    }

    /** An empty signature takes the one adopted, with one click; else the signer adopts one, or another one. */
    onClickImage(field) {
        this.activate(field);
        this.state.error = false;
        const adopted = this.state.adopted[field.type];
        if (!this.value(field) && adopted) {
            this.state.values[field.id] = adopted;
            return;
        }
        this.dialog.add(SignFieldDialog, {
            type: field.type,
            name: this.defaultName,
            onAdopt: ({ name, image }) => {
                this.state.adopted[field.type] = image;
                this.state.values[field.id] = image;
                if (name && field.type === "signature") {
                    this.state.signedName = name;
                }
            },
            onClear: this.value(field) ? () => (this.state.values[field.id] = false) : undefined,
        });
    }

    dismissError() {
        this.state.error = false;
    }

    openDecline() {
        this.dialog.add(SignDeclineDialog, { action: `${this.props.baseUrl}/decline` });
    }

    download() {
        redirect(this.downloadUrl);
    }

    // ------------------------------------------------------------------
    // Signing
    // ------------------------------------------------------------------

    async finish() {
        if (!this.canFinish) {
            this.goNext();
            return;
        }
        const values = {};
        for (const field of this.state.fields) {
            const value = this.value(field);
            values[field.id] =
                typeof value === "string" && !this.isImage(field) ? value.trim().slice(0, TEXT_LIMIT) : value;
        }
        this.state.submitting = true;
        this.state.error = false;
        let result;
        try {
            result = await rpc(`${this.props.baseUrl}/fields/submit`, { values, name: this.defaultName });
        } catch {
            result = { error: _t("The document could not be signed. Check your connection and try again.") };
        }
        if (result.error) {
            this.state.error = result.error;
            this.state.submitting = false;
            return;
        }
        this.state.signed = true;
        redirect(result.redirect_url || this.props.baseUrl);
    }
}

registry.category("public_components").add("om_sign.signing_page", SigningPage);
