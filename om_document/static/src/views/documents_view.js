import { proxy, signal } from "@odoo/owl";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { FileModel } from "@web/core/file_viewer/file_model";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";

const MODEL = "om.documents.document";

/**
 * @param {Object} env
 * @returns {number|false} the folder chosen in the folder panel
 */
function getActiveFolderId(env) {
    const category = env.searchModel?.categories?.find((c) => c.fieldName === "folder_id");
    return (category && category.activeValueId) || env.searchModel?.context?.om_documents_folder_id || false;
}

/**
 * Upload the files dropped or chosen as documents of the active folder.
 *
 * @returns {Promise<number[]>} the ids of the documents
 */
async function uploadFiles(env, orm, notification, files) {
    files = [...files];
    if (!files.length) {
        return [];
    }
    const data = await Promise.all(
        files.map(async (file) => {
            const dataUrl = await getDataURLFromFile(file);
            return { name: file.name, mimetype: file.type, data: dataUrl.split(",")[1] };
        })
    );
    const context = { ...env.searchModel.context };
    for (const key of Object.keys(context)) {
        if (key.startsWith("default_") || key.startsWith("search")) {
            delete context[key];
        }
    }
    const values = {};
    for (const key of ["partner_id", "res_model", "res_id"]) {
        if (env.searchModel.context[`default_${key}`]) {
            values[key] = env.searchModel.context[`default_${key}`];
        }
    }
    const ids = await orm.call(MODEL, "upload_files", [getActiveFolderId(env), data, values], { context });
    notification.add(_t("%s file(s) uploaded.", ids.length), { type: "success" });
    return ids;
}

/**
 * Reload the documents and the counters of the folder panel.
 */
async function reloadDocuments(env, model) {
    if (env.searchModel?._notify) {
        await env.searchModel._notify();
    } else {
        await model.load();
    }
}

/**
 * @param {Object} record a record of the documents view
 * @returns {FileModel|null} the file of the record, as the file viewer takes it
 */
function recordToFile(record) {
    const attachment = record.data.attachment_id;
    const attachmentId = attachment && (attachment.id || attachment[0]);
    if (record.data.type === "url" && record.data.url) {
        return Object.assign(new FileModel(), {
            id: record.resId,
            name: record.data.name,
            type: "url",
            url: record.data.url,
        });
    }
    if (!attachmentId) {
        return null;
    }
    return Object.assign(new FileModel(), {
        id: attachmentId,
        name: record.data.file_name || record.data.name,
        mimetype: record.data.mimetype,
        checksum: record.data.checksum,
        type: "binary",
    });
}

/**
 * The buttons and the drag and drop of the documents views, shared by the kanban and the list.
 */
const DocumentsControllerMixin = (T) =>
    class extends T {
        setup() {
            super.setup();
            this.orm = useService("orm");
            this.notification = useService("notification");
            this.fileInputRef = signal.ref();
        }

        get activeFolderId() {
            return getActiveFolderId(this.env);
        }

        onClickUpload() {
            this.fileInputRef().click();
        }

        async onFileInputChange(ev) {
            const ids = await uploadFiles(this.env, this.orm, this.notification, ev.target.files);
            ev.target.value = "";
            if (ids.length) {
                await reloadDocuments(this.env, this.model);
            }
        }

        get documentsActionContext() {
            const context = { ...this.props.context };
            const folderId = this.activeFolderId;
            if (folderId) {
                context.om_documents_folder_id = folderId;
                context.default_folder_id = folderId;
            }
            return context;
        }

        onClickAddLink() {
            this.actionService.doAction(
                {
                    type: "ir.actions.act_window",
                    name: _t("Add a Link"),
                    res_model: MODEL,
                    views: [[false, "form"]],
                    target: "new",
                    context: { ...this.documentsActionContext, default_type: "url" },
                },
                { onClose: () => reloadDocuments(this.env, this.model) }
            );
        }

        onClickRequest() {
            this.actionService.doAction("om_document.action_request_wizard", {
                additionalContext: this.documentsActionContext,
                onClose: () => reloadDocuments(this.env, this.model),
            });
        }

        async onClickShareFolder() {
            const folderId = this.activeFolderId;
            if (!folderId) {
                return;
            }
            const action = await this.orm.call("om.documents.folder", "action_share", [[folderId]]);
            this.actionService.doAction(action);
        }
    };

/**
 * The drop zone of the documents views: files dropped on the view are uploaded in the active folder.
 */
const DocumentsRendererMixin = (T) =>
    class extends T {
        setup() {
            super.setup();
            this.orm = useService("orm");
            this.notification = useService("notification");
            this.dropState = proxy({ visible: false });
        }

        onDragEnter(ev) {
            if (ev.dataTransfer?.types.includes("Files")) {
                this.dropState.visible = true;
            }
        }

        onDragLeave(ev) {
            if (!ev.currentTarget.contains(ev.relatedTarget)) {
                this.dropState.visible = false;
            }
        }

        async onDrop(ev) {
            this.dropState.visible = false;
            const files = ev.dataTransfer?.files;
            if (!files?.length) {
                return;
            }
            const ids = await uploadFiles(this.env, this.orm, this.notification, files);
            if (ids.length) {
                await reloadDocuments(this.env, this.props.list.model);
            }
        }
    };

export class DocumentsKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    }

    preview() {
        const file = recordToFile(this.props.record);
        if (!file || !file.isViewable) {
            return false;
        }
        const files = this.props.record.model.root.records
            .map(recordToFile)
            .filter((f) => f && f.isViewable);
        const current = files.find((f) => f.id === file.id && f.type === file.type) || file;
        this.fileViewer.open(current, files.includes(current) ? files : [current]);
        return true;
    }

    triggerAction(params) {
        if (params.type === "preview") {
            if (!this.preview()) {
                this.props.openRecord(this.props.record);
            }
            return;
        }
        return super.triggerAction(params);
    }

    onGlobalClick(ev, newWindow) {
        if (
            !newWindow &&
            !ev.altKey &&
            !this.props.getSelection().length &&
            !ev.target.closest(this.constructor.CANCEL_GLOBAL_CLICK) &&
            this.preview()
        ) {
            return;
        }
        return super.onGlobalClick(ev, newWindow);
    }
}

export class DocumentsKanbanRenderer extends DocumentsRendererMixin(KanbanRenderer) {
    static template = "om_document.DocumentsKanbanRenderer";
    static components = { ...KanbanRenderer.components, KanbanRecord: DocumentsKanbanRecord };
}

export class DocumentsKanbanController extends DocumentsControllerMixin(KanbanController) {}

export class DocumentsListRenderer extends DocumentsRendererMixin(ListRenderer) {
    static template = "om_document.DocumentsListRenderer";
}

export class DocumentsListController extends DocumentsControllerMixin(ListController) {}

registry.category("views").add("om_documents_kanban", {
    ...kanbanView,
    Controller: DocumentsKanbanController,
    Renderer: DocumentsKanbanRenderer,
    buttonTemplate: "om_document.DocumentsKanbanButtons",
});

registry.category("views").add("om_documents_list", {
    ...listView,
    Controller: DocumentsListController,
    Renderer: DocumentsListRenderer,
    buttonTemplate: "om_document.DocumentsListButtons",
});
