import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const MODEL = "document.document";

/**
 * The documents of a record as cards: one per document, coloured by how close
 * it is to expiring, and one dashed card per type the record has no document
 * of yet. A file dropped on a card is attached to its document, or creates the
 * missing document with it. Clicking a card opens the document in a dialog.
 */
export class DocumentBoardField extends Component {
    static template = "om_document.DocumentBoardField";
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
        this.state = proxy({ documents: [], missing: [], canEdit: false, dragOver: null, busy: false });
        onWillStart(() => this.load());
    }

    get record() {
        return this.props.record;
    }

    get resModel() {
        return this.record.resModel;
    }

    get resId() {
        return this.record.resId;
    }

    get editable() {
        return Boolean(this.resId) && this.state.canEdit && !this.props.readonly;
    }

    async load() {
        if (!this.resId) {
            return;
        }
        const data = await this.orm.call(MODEL, "board_data", [this.resModel, this.resId]);
        Object.assign(this.state, { documents: data.documents, missing: data.missing, canEdit: data.can_edit });
    }

    async refresh() {
        await this.load();
        // the smart buttons count the documents: reload them unless the form holds unsaved changes
        if (!(await this.record.isDirty())) {
            await this.record.load();
        }
    }

    // badges

    badge(doc) {
        if (doc.state === "expired") {
            return { cls: "text-bg-danger", label: _t("Expired %s", doc.date_expiry) };
        }
        if (doc.state === "expiring") {
            const label = doc.days_left === 0 ? _t("Expires today") : _t("Expires in %s days", doc.days_left);
            return { cls: "text-bg-warning", label };
        }
        if (doc.state === "valid") {
            return { cls: "text-bg-success", label: _t("Valid until %s", doc.date_expiry) };
        }
        return { cls: "text-bg-light border", label: _t("No expiry") };
    }

    fileIcon(attachment) {
        const mimetype = attachment.mimetype || "";
        if (mimetype === "application/pdf") {
            return "picture_as_pdf";
        }
        if (mimetype.startsWith("image/")) {
            return "image";
        }
        return "description";
    }

    isImage(attachment) {
        return (attachment.mimetype || "").startsWith("image/");
    }

    // dialogs

    openDialog(resId, context = {}) {
        this.dialog.add(FormViewDialog, {
            resModel: MODEL,
            resId: resId || false,
            title: resId ? _t("Document") : _t("New Document"),
            context: { default_res_model: this.resModel, default_res_id: this.resId, ...context },
            onRecordSaved: () => this.refresh(),
        });
    }

    open(doc) {
        this.openDialog(doc.id);
    }

    add(type) {
        this.openDialog(false, type ? { default_type_id: type.id } : {});
    }

    async renew(doc) {
        const action = await this.orm.call(MODEL, "action_renew", [[doc.id]]);
        this.openDialog(false, action.context);
    }

    preview(doc, attachment) {
        const files = doc.attachments.map((file) =>
            this.store["ir.attachment"].insert({ id: file.id, name: file.name, mimetype: file.mimetype })
        );
        const file = files.find((item) => item.id === attachment.id);
        if (file?.isViewable) {
            this.fileViewer.open(file, files);
        } else {
            window.open(`/web/content/${attachment.id}?download=true`, "_blank");
        }
    }

    // drag and drop

    onDragOver(ev, key) {
        if (!this.editable || !ev.dataTransfer?.types.includes("Files")) {
            return;
        }
        ev.preventDefault();
        this.state.dragOver = key;
    }

    onDragLeave(ev, key) {
        if (this.state.dragOver === key && !ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.dragOver = null;
        }
    }

    async onDrop(ev, { doc, type }) {
        ev.preventDefault();
        this.state.dragOver = null;
        const dropped = [...(ev.dataTransfer?.files || [])];
        if (!this.editable || !dropped.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const files = await Promise.all(dropped.map(async (file) => ({
                name: file.name,
                mimetype: file.type,
                data: (await getDataURLFromFile(file)).split(",")[1],
            })));
            const documentId = await this.orm.call(MODEL, "board_upload", [
                this.resModel, this.resId, type ? type.id : false, doc ? doc.id : false, files,
            ]);
            await this.refresh();
            this.notification.add(
                files.length === 1 ? _t("%s added.", files[0].name) : _t("%s files added.", files.length),
                { type: "success" }
            );
            if (!doc) {
                // a new document: fill in its number and dates
                this.openDialog(documentId);
            }
        } finally {
            this.state.busy = false;
        }
    }
}

export const documentBoardField = {
    component: DocumentBoardField,
    displayName: _t("Documents"),
    supportedTypes: ["one2many"],
    relatedFields: () => [{ name: "display_name", type: "char" }],
    isEmpty: () => false,
};

registry.category("fields").add("om_document_board", documentBoardField);
