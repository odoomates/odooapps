import { Component, onMounted, onWillUnmount, proxy, signal, useProps } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { imageUrl } from "@web/core/utils/urls";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const WORKER = "/web/static/lib/pdfjs/build/pdf.worker.js";
// the width of the picture of the first page, in pixels
const THUMBNAIL_WIDTH = 360;

// the pages are drawn one after the other, not all the cards of the view at once
let queue = Promise.resolve();
function enqueue(job) {
    const run = queue.then(job, job);
    queue = run.catch(() => {});
    return run;
}

/**
 * Draws the first page of a PDF into an image, in base64 as a data URI.
 */
async function drawFirstPage(url) {
    await loadPDFJSAssets();
    if (!globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc) {
        globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc = WORKER;
    }
    const pdf = await globalThis.pdfjsLib.getDocument({ url }).promise;
    try {
        const page = await pdf.getPage(1);
        const { width } = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: THUMBNAIL_WIDTH / width });
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const context = canvas.getContext("2d");
        // a page without a background is white, not transparent
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        await page.render({ canvasContext: context, viewport }).promise;
        return canvas.toDataURL("image/jpeg", 0.85);
    } finally {
        pdf.destroy();
    }
}

/**
 * The first page of the PDF of a sign template, on its card. Kept by the server once drawn; until then, drawn here
 * by pdf.js when the card comes into view, then given to the server to keep (when the user may change the template).
 */
export class SignThumbnailField extends Component {
    static template = "om_sign.ThumbnailField";
    props = useProps({ ...standardFieldProps });
    box = signal.ref();

    setup() {
        // not bound to the component: the picture drawn is kept even when the user left the view meanwhile
        this.orm = this.env.services.orm;
        this.state = proxy({ drawn: "", failed: false });
        this.gone = false;
        onMounted(() => this.observe());
        onWillUnmount(() => {
            this.gone = true;
            this.observer?.disconnect();
        });
    }

    get record() {
        return this.props.record;
    }

    get isSample() {
        return Boolean(this.record.model.useSampleModel);
    }

    get url() {
        if (this.state.drawn) {
            return this.state.drawn;
        }
        if (!this.record.data[this.props.name] || this.isSample) {
            return "";
        }
        return imageUrl(this.record.resModel, this.record.resId, this.props.name, {
            unique: this.record.data.document_checksum || "",
        });
    }

    observe() {
        if (this.url || this.isSample || !this.record.resId || !window.IntersectionObserver) {
            return;
        }
        this.observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                this.observer.disconnect();
                this.draw();
            }
        });
        this.observer.observe(this.box());
    }

    async draw() {
        const { resId, resModel } = this.record;
        const checksum = this.record.data.document_checksum;
        let drawn;
        try {
            drawn = await enqueue(() => drawFirstPage(`/web/content/${resModel}/${resId}/document_file`));
        } catch {
            if (!this.gone) {
                this.state.failed = true;
            }
            return;
        }
        if (!this.gone) {
            this.state.drawn = drawn;
        }
        if (checksum) {
            // kept for the next time, for everyone; refused when the user may not change the template
            await this.orm.silent.call(resModel, "save_thumbnail", [[resId], drawn, checksum]);
        }
    }
}

registry.category("fields").add("om_sign_thumbnail", {
    component: SignThumbnailField,
    displayName: _t("Sign Thumbnail"),
    supportedTypes: ["binary"],
    fieldDependencies: [{ name: "document_checksum", type: "char" }],
});

const SIGNER_STATES = {
    waiting: { icon: "schedule", label: _t("Waiting for others"), color: "secondary" },
    to_sign: { icon: "edit", label: _t("To sign"), color: "warning" },
    signed: { icon: "check", label: _t("Signed"), color: "success" },
    declined: { icon: "close", label: _t("Declined"), color: "danger" },
};

/**
 * The signers of a request, as avatars marked with their status, in their order.
 */
export class SignSignersField extends Component {
    static template = "om_sign.SignersField";
    props = useProps({ ...standardFieldProps });

    get signers() {
        const signers = this.props.record.data[this.props.name];
        return Array.isArray(signers) ? signers : [];
    }

    avatar(signer) {
        return signer.partner_id ? `/web/image/res.partner/${signer.partner_id}/avatar_128` : "";
    }

    status(signer) {
        return SIGNER_STATES[signer.state] || SIGNER_STATES.waiting;
    }

    title(signer) {
        const role = signer.role ? ` (${signer.role})` : "";
        return `${signer.name}${role}: ${this.status(signer).label}`;
    }
}

registry.category("fields").add("om_sign_signers", {
    component: SignSignersField,
    displayName: _t("Sign Signers"),
    supportedTypes: ["json"],
});

/**
 * Each signer of a request in their order, with what they did and when: asked, opened, email confirmed, signed or
 * declined.
 */
export class SignTimelineField extends Component {
    static template = "om_sign.TimelineField";
    props = useProps({ ...standardFieldProps });

    get signers() {
        const signers = this.props.record.data[this.props.name];
        return Array.isArray(signers) ? signers : [];
    }

    avatar(signer) {
        return signer.partner_id ? `/web/image/res.partner/${signer.partner_id}/avatar_128` : "";
    }

    status(signer) {
        return SIGNER_STATES[signer.state] || SIGNER_STATES.waiting;
    }

    date(value) {
        // e.g. Oct 31, 5:52 PM; the year when it is not this one
        if (!value) {
            return "";
        }
        const date = deserializeDateTime(value).setZone("default");
        const sameYear = date.year === luxon.DateTime.now().year;
        return date.toLocaleString({
            month: "short",
            day: "numeric",
            year: sameYear ? undefined : "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    }

    steps(signer) {
        const steps = [
            { key: "invited", label: _t("Asked to sign"), date: signer.date_invited, icon: "mail" },
            { key: "opened", label: _t("Opened"), date: signer.date_opened, icon: "visibility" },
        ];
        if (signer.date_verified) {
            steps.push({ key: "verified", label: _t("Email verified"), date: signer.date_verified, icon: "verified" });
        }
        if (signer.state === "signed") {
            steps.push({ key: "signed", label: _t("Signed"), date: signer.date_signed, icon: "check_circle" });
        } else if (signer.state === "declined") {
            steps.push({ key: "declined", label: _t("Declined"), date: "", icon: "cancel" });
        } else {
            steps.push({ key: "signed", label: _t("Signed"), date: "", icon: "check_circle" });
        }
        return steps;
    }
}

registry.category("fields").add("om_sign_timeline", {
    component: SignTimelineField,
    displayName: _t("Sign Timeline"),
    supportedTypes: ["json"],
});
